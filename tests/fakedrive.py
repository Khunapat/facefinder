"""A stand-in for Google Drive backed by local folders.

Used by the tests, and by tests/devserver.py to try the whole app without
Google credentials. The app itself never imports this.

    album  -> the photos under tests/img (plus tests/img_extra when present)
    copies -> real files written under an output directory, one folder per person
"""
import glob
import os
import shutil

import httplib2
from fastapi import Request
from fastapi.responses import RedirectResponse
from googleapiclient.errors import HttpError

HERE = os.path.dirname(os.path.abspath(__file__))
ALBUM_ID = "demo-album-000000000000000"
LOCKED_ID = "locked-folder-00000000000000"      # a destination that refuses writes
ALBUM_URL = "https://drive.google.com/drive/folders/" + ALBUM_ID
LOCKED_URL = "https://drive.google.com/drive/folders/" + LOCKED_ID


class _Req:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Files:
    def get(self, fileId=None, **_):
        return _Req({"id": fileId, "name": fileId})


class _Service:
    def files(self):
        return _Files()


class FakeDrive:
    def __init__(self, out_dir: str, image_dirs=None):
        self.out_dir = out_dir
        self.image_dirs = image_dirs or [
            os.path.join(HERE, "img"),
            os.path.join(HERE, "img_extra"),
        ]
        self.folders = {}       # id -> {"id", "name", "parent", "path"}
        self.copies = {}        # folder id -> set of source file ids
        self.copy_calls = 0

    # -- reading the album --------------------------------------------------
    def _images(self):
        out = {}
        for d in self.image_dirs:
            for p in sorted(glob.glob(os.path.join(d, "*.jp*g"))):
                out[os.path.basename(p)] = p
        return out

    def folder_meta(self, svc, folder_id):
        from app import google_drive as gd

        if folder_id == ALBUM_ID:
            return {"id": ALBUM_ID, "name": "Graduation 2026 (demo)", "mimeType": gd.FOLDER_MIME}
        if folder_id == LOCKED_ID:
            return {"id": LOCKED_ID, "name": "Locked folder", "mimeType": gd.FOLDER_MIME}
        if folder_id in self.folders:
            f = self.folders[folder_id]
            return {"id": f["id"], "name": f["name"], "mimeType": gd.FOLDER_MIME}
        raise FileNotFoundError(folder_id)

    def list_images(self, svc, folder_id, recursive=True):
        return [{"id": n, "name": n, "mimeType": "image/jpeg",
                 "imageMediaMetadata": {"time": "2026:06:%02d 09:%02d:00" % (12 + i // 3, (i % 3) * 10)}}
                for i, n in enumerate(sorted(self._images()))]

    def fetch_image_bytes(self, creds, svc, file_meta, size=None):
        with open(self._images()[file_meta["id"]], "rb") as fh:
            return fh.read()

    # -- writing the copies -------------------------------------------------
    def ensure_folder(self, svc, name, parent=None):
        if parent == LOCKED_ID:
            raise HttpError(httplib2.Response({"status": 403}), b"insufficient permissions")
        for f in self.folders.values():
            if f["name"] == name and f["parent"] == parent:
                return {"id": f["id"], "name": name}
        base = self.folders[parent]["path"] if parent else self.out_dir
        fid = "fld-%d-%s" % (len(self.folders) + 1, "x" * 20)
        path = os.path.join(base, name)
        os.makedirs(path, exist_ok=True)
        self.folders[fid] = {"id": fid, "name": name, "parent": parent, "path": path}
        self.copies[fid] = set()
        return {"id": fid, "name": name}

    def copied_sources(self, svc, folder_id):
        return set(self.copies.get(folder_id, ()))

    def copy_into(self, svc, file_id, dest_folder_id):
        self.copy_calls += 1
        shutil.copy(self._images()[file_id], self.folders[dest_folder_id]["path"])
        self.copies[dest_folder_id].add(file_id)
        return {"id": "copy-" + file_id, "name": file_id}

    def tree(self):
        """{folder path relative to out_dir: sorted file names} for assertions."""
        out = {}
        for f in self.folders.values():
            rel = os.path.relpath(f["path"], self.out_dir).replace(os.sep, "/")
            out[rel] = sorted(n for n in os.listdir(f["path"]) if os.path.isfile(os.path.join(f["path"], n)))
        return out


def install(out_dir: str, image_dirs=None) -> FakeDrive:
    """Swap the app's Drive layer for a FakeDrive and add a /dev/login route."""
    from app import google_drive as gd
    from app import main

    fake = FakeDrive(out_dir, image_dirs)
    gd.creds_from_session = lambda data: type("Creds", (), {"token": "dev"})()
    gd.creds_to_session = lambda creds: {"token": "dev"}
    gd.service = lambda creds: _Service()
    for name in (
        "folder_meta", "list_images", "fetch_image_bytes",
        "ensure_folder", "copied_sources", "copy_into",
    ):
        setattr(gd, name, getattr(fake, name))

    def dev_login(request: Request):
        request.session["creds"] = {"token": "dev"}
        request.session["user"] = {"emailAddress": "demo@example.com"}
        return RedirectResponse("/")

    main.app.add_api_route("/dev/login", dev_login, methods=["GET"])
    return fake
