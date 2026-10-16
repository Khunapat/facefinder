"""Thin wrapper over the Drive v3 API: list an album, fetch pixels, copy files."""
import datetime
import io
import logging
import re

import requests
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from . import config

IMAGE_MIMES = ("image/jpeg", "image/png", "image/heic", "image/webp", "image/jpg")
FOLDER_MIME = "application/vnd.google-apps.folder"

log = logging.getLogger("facefinder")


def creds_from_session(data: dict) -> Credentials:
    # The expiry has to make the round trip. Without it google-auth leaves
    # expiry=None, which makes .expired False and .valid True forever, so the
    # refresh below never fires and the access token silently goes stale after
    # about an hour.
    stamp = data.get("expiry")
    expiry = None
    if stamp:
        expiry = datetime.datetime.fromtimestamp(
            stamp, datetime.timezone.utc
        ).replace(tzinfo=None)  # google-auth compares against naive UTC
    c = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        scopes=config.SCOPES,
        expiry=expiry,
    )
    if not c.valid and c.refresh_token:
        c.refresh(Request())
    return c


def creds_to_session(c: Credentials) -> dict:
    return {
        "token": c.token,
        "refresh_token": c.refresh_token,
        "expiry": c.expiry.replace(tzinfo=datetime.timezone.utc).timestamp()
        if c.expiry
        else None,
    }


def _authed_session(creds: Credentials) -> AuthorizedSession:
    """One AuthorizedSession per credentials object, kept for connection reuse.

    Unlike a bare requests.get with a hand-built Authorization header, this
    refreshes the token when it expires and retries a 401, which is what keeps
    the thumbnail path alive through a long scan.
    """
    s = getattr(creds, "_ff_session", None)
    if s is None:
        s = AuthorizedSession(creds)
        creds._ff_session = s
    return s


def service(creds: Credentials):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def parse_folder_id(value: str) -> str:
    """Accept a raw ID or any of the Drive URL shapes people actually paste."""
    value = (value or "").strip()
    if not value:
        return ""
    for pat in (
        r"/folders/([a-zA-Z0-9_-]{10,})",
        r"[?&]id=([a-zA-Z0-9_-]{10,})",
        r"/d/([a-zA-Z0-9_-]{10,})",
    ):
        m = re.search(pat, value)
        if m:
            return m.group(1)
    return value.split("?")[0].split("/")[-1]


def folder_meta(svc, folder_id: str) -> dict:
    return svc.files().get(
        fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True
    ).execute()


def list_images(svc, folder_id: str, recursive: bool = True) -> list:
    """Every image under the folder. Subfolders are walked breadth-first."""
    out, queue, seen = [], [folder_id], set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        page = None
        while True:
            resp = svc.files().list(
                q=f"'{current}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType,size,thumbnailLink,createdTime,imageMediaMetadata(width,time))",
                pageSize=1000,
                pageToken=page,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                if f["mimeType"] == FOLDER_MIME:
                    if recursive:
                        queue.append(f["id"])
                elif f["mimeType"].startswith("image/"):
                    out.append(f)
            page = resp.get("nextPageToken")
            if not page:
                break
    return out


def taken_at(f: dict):
    """When the photo was taken, as 'YYYY-MM-DDTHH:MM:SS': the camera's own time
    when Drive has it (EXIF writes it '2026:06:12 14:03:22'), else the upload time."""
    t = (f.get("imageMediaMetadata") or {}).get("time")
    if t and len(t) >= 19 and t[4] == ":" and t[7] == ":":
        return "%s-%s-%sT%s" % (t[0:4], t[5:7], t[8:10], t[11:19])
    c = f.get("createdTime")
    return c[:19] if c else None


def fetch_image_bytes(creds: Credentials, svc, file_meta: dict, size: int = None) -> bytes:
    """Prefer Drive's own thumbnail: a 1600px JPEG instead of a 12 MB RAW-ish
    original is ~50x less bandwidth and plenty for face embedding."""
    link = file_meta.get("thumbnailLink")
    name = file_meta.get("name", file_meta.get("id", "?"))
    why = "Drive returned no thumbnailLink"
    if link:
        url = re.sub(r"=s\d+(-c)?$", f"=s{size or config.THUMB_SIZE}", link)
        try:
            r = _authed_session(creds).get(url, timeout=30)
            if r.ok and len(r.content) > 1024:
                return r.content
            why = "thumbnail fetch returned HTTP %s" % r.status_code
        except requests.RequestException as e:
            why = "thumbnail fetch failed: %s" % type(e).__name__

    # Falling back means pulling the full-size original - on a DSLR album that
    # is tens of MB per photo instead of a few hundred KB. Say so, because
    # otherwise a scan just mysteriously slows to a crawl.
    log.warning("full-size download for %s (%s)", name, why)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(
        buf, svc.files().get_media(fileId=file_meta["id"], supportsAllDrives=True)
    )
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def ensure_folder(svc, name: str, parent: str = None) -> dict:
    """Find-or-create a folder, so running an export twice reuses the folder.

    With the limited scope the app can only write into folders it made, so it
    only reuses folders carrying its own tag; a same-named folder the user made
    by hand would be found but could not be written to."""
    q = (
        f"name = '{name.replace(chr(39), chr(92) + chr(39))}' "
        f"and mimeType = '{FOLDER_MIME}' and trashed = false "
        f"and '{parent or 'root'}' in parents"
    )
    if config.DRIVE_ACCESS != "full":
        q += " and appProperties has { key='ff' and value='1' }"
    found = svc.files().list(
        q=q,
        fields="files(id,name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    if found:
        return found[0]
    body = {"name": name, "mimeType": FOLDER_MIME, "appProperties": {"ff": "1"}}
    if parent:
        body["parents"] = [parent]
    return svc.files().create(
        body=body, fields="id,name", supportsAllDrives=True
    ).execute()


def copied_sources(svc, folder_id: str) -> set:
    """Source file IDs already copied into this folder by an earlier export."""
    out, page = set(), None
    while True:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(appProperties)",
            pageSize=1000,
            pageToken=page,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for f in resp.get("files", []):
            src = (f.get("appProperties") or {}).get("ff_src")
            if src:
                out.add(src)
        page = resp.get("nextPageToken")
        if not page:
            return out


def copy_into(svc, file_id: str, dest_folder_id: str) -> dict:
    """Server-side copy. Google moves the bytes internally: we never download
    or re-upload the full-resolution photo. The copy remembers which file it
    came from so a second export can skip it."""
    body = {"parents": [dest_folder_id], "appProperties": {"ff_src": file_id}}
    return svc.files().copy(
        fileId=file_id, body=body, fields="id,name", supportsAllDrives=True
    ).execute()
