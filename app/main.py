"""FaceFinder - find every photo of one person in a shared Drive album."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from google_auth_oauthlib.flow import Flow
from starlette.middleware.sessions import SessionMiddleware

from . import config, faces
from . import google_drive as gd
from . import store

app = FastAPI(title="FaceFinder")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    same_site="lax",
    https_only=config.PUBLIC_BASE_URL.startswith("https"),
)

STATIC = os.path.join(os.path.dirname(__file__), "static")
_jobs = {}          # folder_id -> running index thread
_jobs_lock = threading.Lock()


# --------------------------------------------------------------- auth -----
def _flow(state: str = None) -> Flow:
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(500, "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [config.REDIRECT_URI],
            }
        },
        scopes=config.SCOPES,
        state=state,
        redirect_uri=config.REDIRECT_URI,
    )


def _creds(request: Request):
    data = request.session.get("creds")
    if not data:
        raise HTTPException(401, "Not signed in to Google")
    return gd.creds_from_session(data)


@app.get("/oauth2/login")
def login(request: Request):
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    request.session["oauth_state"] = state
    # google-auth-oauthlib turns on PKCE by default: authorization_url() above
    # generated a code_verifier and sent its challenge to Google. The callback
    # builds a fresh Flow, so unless we carry the verifier across in the session
    # the token exchange fails with "invalid_grant: Missing code verifier".
    request.session["code_verifier"] = flow.code_verifier
    return RedirectResponse(url)


@app.get("/oauth2/callback")
def callback(request: Request):
    flow = _flow(state=request.session.get("oauth_state"))
    flow.code_verifier = request.session.get("code_verifier")
    url = str(request.url)
    # Hosts terminate TLS in front of us, so the URL we see can say http.
    if config.PUBLIC_BASE_URL.startswith("https") and url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    flow.fetch_token(authorization_response=url)
    creds = flow.credentials
    request.session["creds"] = gd.creds_to_session(creds)
    try:
        info = (
            gd.service(creds)
            .about()
            .get(fields="user(emailAddress,displayName)")
            .execute()
        )
        request.session["user"] = info.get("user", {})
    except Exception:
        request.session["user"] = {}
    return RedirectResponse("/")


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {
        "signed_in": bool(request.session.get("creds")),
        "user": request.session.get("user", {}),
        "configured": bool(config.GOOGLE_CLIENT_ID),
        "default_threshold": config.DEFAULT_THRESHOLD,
    }


# -------------------------------------------------------------- album -----
@app.post("/api/album")
async def open_album(request: Request):
    body = await request.json()
    folder_id = gd.parse_folder_id(body.get("folder", ""))
    if not folder_id:
        raise HTTPException(400, "Paste a Google Drive folder link")
    creds = _creds(request)
    svc = gd.service(creds)
    try:
        meta = gd.folder_meta(svc, folder_id)
    except Exception as e:
        raise HTTPException(
            404, "Cannot open that folder. Check it is shared with your account."
        ) from e
    if meta["mimeType"] != gd.FOLDER_MIME:
        raise HTTPException(400, "That link points at a file, not a folder")
    if store.album(folder_id) is None:
        store.set_album(folder_id, name=meta["name"], status="pending")
    return {
        "folder_id": folder_id,
        "name": meta["name"],
        "status": dict(store.album(folder_id)),
    }


def _index_worker(folder_id: str, creds_data: dict):
    """Walk the album once and cache an embedding for every face found."""
    try:
        creds = gd.creds_from_session(creds_data)
        svc = gd.service(creds)
        files = gd.list_images(svc, folder_id)
        already = store.indexed_file_ids(folder_id)
        todo = [f for f in files if f["id"] not in already]
        store.set_album(
            folder_id,
            status="indexing",
            total=len(files),
            done=len(already),
            message="%d new photos to scan" % len(todo),
        )
        faces.engine()   # load the model once, before the pool starts

        def one(meta):
            try:
                data = gd.fetch_image_bytes(creds, svc, meta)
                found = faces.embed_image(data)
            except Exception:
                found = []
            store.save_photo(folder_id, meta["id"], meta["name"], found)
            store.bump_progress(folder_id, 1, len(found))

        with ThreadPoolExecutor(max_workers=config.INDEX_WORKERS) as pool:
            list(pool.map(one, todo))

        row = store.album(folder_id)
        store.set_album(
            folder_id,
            status="ready",
            message="%d faces across %d photos" % (row["faces"], row["done"]),
        )
    except Exception as e:
        store.set_album(folder_id, status="error", message=str(e)[:300])
    finally:
        with _jobs_lock:
            _jobs.pop(folder_id, None)


@app.post("/api/index")
async def start_index(request: Request):
    body = await request.json()
    folder_id = body.get("folder_id")
    if not folder_id:
        raise HTTPException(400, "folder_id required")
    _creds(request)
    if body.get("rebuild"):
        store.clear_album(folder_id)
        store.set_album(folder_id, status="pending")
    with _jobs_lock:
        if folder_id in _jobs:
            return {"started": False, "reason": "already running"}
        t = threading.Thread(
            target=_index_worker,
            args=(folder_id, request.session["creds"]),
            daemon=True,
        )
        _jobs[folder_id] = t
    t.start()
    return {"started": True}


@app.get("/api/album/{folder_id}/status")
def album_status(folder_id: str):
    row = store.album(folder_id)
    if row is None:
        raise HTTPException(404, "Unknown album")
    return dict(row)


# ------------------------------------------------------------- search -----
@app.post("/api/search")
async def search(
    request: Request,
    folder_id: str = Form(...),
    threshold: float = Form(config.DEFAULT_THRESHOLD),
    selfies: list[UploadFile] = File(...),
):
    _creds(request)
    images = [await f.read() for f in selfies]
    query = faces.best_query_vector(images)
    if query is None:
        raise HTTPException(
            400,
            "No face found in the photo you uploaded. "
            "Try a clearer, front-facing one.",
        )
    mat, meta = store.load_matrix(folder_id)
    if not meta:
        raise HTTPException(400, "This album has not been scanned yet.")
    if mat.shape[1] != query.shape[0]:
        raise HTTPException(
            400, "The album was indexed with a different model. Rebuild the index."
        )

    sims = mat @ query                       # both sides are L2-normalised
    best = {}                                # keep only each photo's best face
    for i, s in enumerate(sims):
        m = meta[i]
        if s > best.get(m["file_id"], (-1.0, None))[0]:
            best[m["file_id"]] = (float(s), m)

    hits = [
        {
            "file_id": fid,
            "name": m["name"],
            "score": round(s, 4),
            "bbox": m["bbox"],
            "confident": s >= threshold + 0.12,
        }
        for fid, (s, m) in best.items()
        if s >= threshold
    ]
    hits.sort(key=lambda h: -h["score"])
    return {
        "count": len(hits),
        "scanned": len(best),
        "threshold": threshold,
        "matches": hits[:500],
    }


@app.get("/api/thumb/{file_id}")
def thumb(request: Request, file_id: str):
    creds = _creds(request)
    svc = gd.service(creds)
    meta = (
        svc.files()
        .get(fileId=file_id, fields="id,name,thumbnailLink", supportsAllDrives=True)
        .execute()
    )
    return Response(
        content=gd.fetch_image_bytes(creds, svc, meta),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# --------------------------------------------------------------- copy -----
@app.post("/api/copy")
async def copy(request: Request):
    body = await request.json()
    file_ids = body.get("file_ids") or []
    if not file_ids:
        raise HTTPException(400, "Nothing selected")
    creds = _creds(request)
    svc = gd.service(creds)

    dest = body.get("dest_folder_id")
    if dest:
        dest_id = gd.parse_folder_id(dest)
        dest_name = gd.folder_meta(svc, dest_id)["name"]
    else:
        folder = gd.ensure_folder(svc, body.get("dest_name") or "My Graduation Photos")
        dest_id, dest_name = folder["id"], folder["name"]

    copied, failed = 0, []
    for fid in file_ids:
        try:
            gd.copy_into(svc, fid, dest_id)
            copied += 1
        except Exception as e:
            failed.append({"file_id": fid, "error": str(e)[:150]})
    return {
        "copied": copied,
        "failed": failed,
        "dest_id": dest_id,
        "dest_name": dest_name,
        "dest_url": "https://drive.google.com/drive/folders/" + dest_id,
    }


# --------------------------------------------------------------- page -----
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
