"""FaceFinder - sort a shared Drive album into one folder per person."""
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from google_auth_oauthlib.flow import Flow
from googleapiclient.errors import HttpError
from starlette.middleware.sessions import SessionMiddleware

from . import cluster, config, curate, faces, gemini
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
_exports = {}       # job_id -> progress dict, read by the page while it runs
_mat_cache = {}     # folder_id -> (stamp, matrix, meta)
_people_cache = {}  # (folder_id, faces, threshold) -> grouped people
_face_cache = {}    # (folder_id, file_id, face_idx) -> small JPEG, memory only
_sorts = {}         # job_id -> sort-by-description progress and result


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
    creds = gd.creds_from_session(data)
    # creds_from_session may have refreshed; keep the new token so the next
    # request does not refresh all over again.
    fresh = gd.creds_to_session(creds)
    if fresh != data:
        request.session["creds"] = fresh
    return creds


def _need_album(request: Request, folder_id: str):
    """The index is shared between users, so a session may only read an album
    it has itself opened through Drive (which is where access is checked)."""
    if not folder_id or folder_id not in request.session.get("albums", []):
        raise HTTPException(403, "Open the album first")


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
        "drive_access": config.DRIVE_ACCESS,
        "gemini": gemini.enabled(),
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
    opened = [a for a in request.session.get("albums", []) if a != folder_id]
    request.session["albums"] = (opened + [folder_id])[-20:]
    return {
        "folder_id": folder_id,
        "name": meta["name"],
        "status": dict(store.album(folder_id)),
    }


def _index_worker(folder_id: str, creds_data: dict):
    """Walk the album once: cache an embedding for every face found, a burst
    fingerprint for every photo and, when Gemini is on, its judgement of the
    photo. Photos scanned before Gemini was switched on get judged too."""
    gem = None
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
        local = threading.local()   # Drive clients are not thread-safe
        # Gemini calls wait on the network, not the CPU, so they get their own,
        # wider pool and run alongside the face scan.
        if gemini.enabled():
            gem = ThreadPoolExecutor(max_workers=config.GEMINI_WORKERS)

        def judge(file_id, data):
            try:
                store.save_ai(folder_id, file_id, gemini.judge(gemini.shrink(data)))
            except Exception:
                pass            # left unjudged; the next scan retries it

        def drive_svc():
            if not hasattr(local, "svc"):
                local.svc = gd.service(creds)
            return local.svc

        def one(meta):
            data = None
            try:
                data = gd.fetch_image_bytes(creds, drive_svc(), meta)
                found, size = faces.analyze(data)
            except Exception:
                found, size = [], None
            store.save_photo(folder_id, meta["id"], meta["name"], found, size,
                             curate.dhash(data) if data else None)
            store.bump_progress(folder_id, 1, len(found))
            if gem and data:
                gem.submit(judge, meta["id"], data)

        def rejudge(meta):
            try:
                data = gd.fetch_image_bytes(creds, drive_svc(), meta, gemini.SEND_SIZE)
            except Exception:
                return
            gem.submit(judge, meta["id"], data)

        with ThreadPoolExecutor(max_workers=config.INDEX_WORKERS) as pool:
            list(pool.map(one, todo))
            if gem:     # scanned earlier, before Gemini was on or when it failed
                fresh = {f["id"] for f in todo}
                missing = {m["id"] for m in store.unjudged(folder_id)} - fresh
                list(pool.map(rejudge, [f for f in files if f["id"] in missing]))
        if gem:
            gem.shutdown(wait=True)

        row = store.album(folder_id)
        msg = "%d faces across %d photos" % (row["faces"], row["done"])
        if gem:
            missed = row["done"] - store.judged_count(folder_id)
            if missed:
                msg += "; Gemini could not check %d (scan again to retry)" % missed
        store.set_album(folder_id, status="ready", message=msg)
    except Exception as e:
        store.set_album(folder_id, status="error", message=str(e)[:300])
    finally:
        if gem:
            gem.shutdown(wait=False, cancel_futures=True)
        with _jobs_lock:
            _jobs.pop(folder_id, None)


@app.post("/api/index")
async def start_index(request: Request):
    body = await request.json()
    folder_id = body.get("folder_id")
    _creds(request)
    _need_album(request, folder_id)
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
    out = dict(row)
    out["judged"] = store.judged_count(folder_id)
    out["gemini"] = gemini.enabled()
    return out


def _matrix(folder_id: str):
    """Embeddings for one album, kept in memory between requests: naming ten
    people is ten searches against the same matrix."""
    row = store.album(folder_id)
    stamp = (row["status"], row["faces"], row["done"]) if row else None
    hit = _mat_cache.get(folder_id)
    if hit and hit[0] == stamp:
        return hit[1], hit[2]
    mat, meta = store.load_matrix(folder_id)
    if row and row["status"] == "ready":
        if len(_mat_cache) >= 4:
            _mat_cache.pop(next(iter(_mat_cache)))
        _mat_cache[folder_id] = (stamp, mat, meta)
    return mat, meta


# ------------------------------------------------------------- search -----
@app.post("/api/search")
def search(
    request: Request,
    folder_id: str = Form(...),
    threshold: float = Form(config.DEFAULT_THRESHOLD),
    selfies: list[UploadFile] = File(...),
):
    """Photos of ONE person. The page calls this once per person it was given."""
    _creds(request)
    _need_album(request, folder_id)
    images = [f.file.read() for f in selfies]
    query = faces.best_query_vector(images)
    if query is None:
        raise HTTPException(
            400,
            "No face found in the photo you uploaded. "
            "Try a clearer, front-facing one.",
        )
    mat, meta = _matrix(folder_id)
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
        "matches": hits[:2000],
    }


GROUPING = {"loose": -0.06, "balanced": 0.0, "strict": 0.06}


@app.post("/api/people")
def people(request: Request, body: dict = Body(...)):
    """Everyone in the album, grouped by face, with no names given."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)
    mat, meta = _matrix(folder_id)
    if not meta:
        raise HTTPException(400, "This album has not been scanned yet.")
    thr = config.CLUSTER_THRESHOLD + GROUPING.get(body.get("grouping"), 0.0)
    if mat.shape[1] < 512:
        thr -= 0.08          # the small fallback model scores lower overall
    key = (folder_id, len(meta), round(thr, 3))
    found = _people_cache.get(key)
    if found is None:
        found = cluster.group_album(mat, meta, thr)
        if len(_people_cache) >= 8:
            _people_cache.pop(next(iter(_people_cache)))
        _people_cache[key] = found
    return {
        "people": found,
        "faces": len(meta),
        "photos": len({m["file_id"] for m in meta}),
    }


@app.get("/api/face/{folder_id}/{file_id}/{face_idx}")
def face(request: Request, folder_id: str, file_id: str, face_idx: int):
    """A small crop of one face, so a person can be recognised and named."""
    creds = _creds(request)
    _need_album(request, folder_id)
    key = (folder_id, file_id, face_idx)
    data = _face_cache.get(key)
    if data is None:
        box = store.face_box(folder_id, file_id, face_idx)
        if box is None:
            raise HTTPException(404, "Unknown face")
        svc = gd.service(creds)
        meta = (
            svc.files()
            .get(fileId=file_id, fields="id,thumbnailLink", supportsAllDrives=True)
            .execute()
        )
        data = faces.crop_face(gd.fetch_image_bytes(creds, svc, meta), box[0], box[1])
        if data is None:
            raise HTTPException(404, "Could not read that photo")
        if len(_face_cache) >= 800:
            _face_cache.pop(next(iter(_face_cache)))
        _face_cache[key] = data
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get("/api/thumb/{file_id}")
def thumb(request: Request, file_id: str, s: int = 0):
    creds = _creds(request)
    svc = gd.service(creds)
    meta = (
        svc.files()
        .get(fileId=file_id, fields="id,name,thumbnailLink", supportsAllDrives=True)
        .execute()
    )
    size = min(max(s, 200), config.THUMB_SIZE) if s else None
    return Response(
        content=gd.fetch_image_bytes(creds, svc, meta, size),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ------------------------------------------------------ Gemini curation -----
def _need_gemini():
    if not gemini.enabled():
        raise HTTPException(
            400, "Gemini is not switched on for this server (set GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY)."
        )


def _ready_photos(folder_id: str) -> list:
    row = store.album(folder_id)
    if row is None or row["status"] != "ready":
        raise HTTPException(400, "Wait for the scan to finish first.")
    return store.photos(folder_id)


@app.post("/api/cull")
def cull(request: Request, body: dict = Body(...)):
    """For the photographer: which frames to keep, which to drop, and why."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)
    out = curate.cull(_ready_photos(folder_id), body.get("strictness") or "normal")
    out["checked"] = store.judged_count(folder_id)
    return out


@app.post("/api/best")
def best(request: Request, body: dict = Body(...)):
    """For the graduate: one person's best photos, out of all of theirs."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)
    file_ids = [f for f in (body.get("file_ids") or []) if isinstance(f, str)][:3000]
    if not file_ids:
        raise HTTPException(400, "No photos given")
    n = max(1, min(int(body.get("n") or 10), 50))
    photos = {p["file_id"]: p for p in _ready_photos(folder_id)}
    mat, meta = _matrix(folder_id)

    # This person's face in each photo: the face nearest to the face all the
    # photos share. Its size in the frame says portrait or crowd shot.
    sizes = {}
    vec = curate.person_vector(mat, meta, file_ids) if len(meta) else None
    if vec is not None:
        sims = mat @ vec
        for i, m in enumerate(meta):
            f = m["file_id"]
            if f in photos and sims[i] > sizes.get(f, (None, None, -1.0))[2]:
                box, size = m["bbox"], photos[f]["size"]
                side = max(box[2] - box[0], box[3] - box[1]) if len(box) == 4 else 0
                frac = side / max(size) if size else 0.0
                sizes[f] = (frac, m["det_score"], float(sims[i]))
    faces_info = {f: (v[0], v[1]) for f, v in sizes.items()}
    ai = {f: p["ai"] for f, p in photos.items()}
    picks = curate.best_shots([f for f in file_ids if f in photos], ai, faces_info, n)
    for p in picks:
        p["name"] = photos[p["file_id"]]["name"]
    return {"best": picks, "of": len(file_ids)}


def _sample_lines(photos: list, limit: int) -> list:
    judged = [p for p in photos if p["ai"]]
    step = max(1, len(judged) // limit)
    return [gemini.as_text(p["ai"]) for p in judged[::step][:limit]]


@app.post("/api/groups/suggest")
def suggest_groups(request: Request, body: dict = Body(...)):
    """Gemini reads the album's descriptions and proposes folders to sort into."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)
    _need_gemini()
    lines = _sample_lines(_ready_photos(folder_id), 150)
    if not lines:
        raise HTTPException(400, "Gemini has not checked any photos in this album yet.")
    try:
        return {"groups": gemini.suggest_groups(lines)}
    except Exception as e:
        raise HTTPException(502, "Gemini did not answer: %s" % str(e)[:160]) from e


def _sort_worker(job: dict, photos: list, groups: list):
    """Put every checked photo into the folders it fits, a batch at a time."""
    try:
        judged = [p for p in photos if p["ai"]]
        batches = [judged[i:i + gemini.SORT_BATCH] for i in range(0, len(judged), gemini.SORT_BATCH)]

        def one(batch):
            try:
                res = gemini.sort_batch([gemini.as_text(p["ai"]) for p in batch], groups)
            except Exception:
                res = [{"groups": [], "sure": False}] * len(batch)
            with job["lock"]:
                for p, r in zip(batch, res):
                    if not r["sure"]:
                        job["check"].append(p["file_id"])
                    elif not r["groups"]:
                        job["none"].append(p["file_id"])
                    for g in r["groups"] if r["sure"] else ():
                        job["groups"][g]["file_ids"].append(p["file_id"])
                job["done"] += len(batch)

        with ThreadPoolExecutor(max_workers=config.GEMINI_WORKERS) as pool:
            list(pool.map(one, batches))
        job["check"].extend(p["file_id"] for p in photos if not p["ai"])
        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)[:300]
    finally:
        job["finished"] = time.time()


@app.post("/api/sort")
def sort_album(request: Request, body: dict = Body(...)):
    """Sort by description. groups: [{name, description}], in Thai or English.
    The result feeds the same export as people: one Drive folder per group."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)
    _need_gemini()
    groups = []
    for g in (body.get("groups") or [])[:12]:
        name = _clean_name(g.get("name"))
        desc = " ".join(str(g.get("description") or name).split())[:300]
        if name:
            groups.append({"name": name, "description": desc})
    if not groups:
        raise HTTPException(400, "Describe at least one group")
    photos = _ready_photos(folder_id)
    for old in [k for k, j in _sorts.items() if time.time() - j.get("finished", 9e18) > 3600]:
        _sorts.pop(old, None)
    job = {
        "status": "running", "folder_id": folder_id, "total": len(photos), "done": 0,
        "groups": [dict(g, file_ids=[]) for g in groups], "check": [], "none": [],
        "message": None, "lock": threading.Lock(),
    }
    job_id = secrets.token_urlsafe(12)
    _sorts[job_id] = job
    threading.Thread(target=_sort_worker, args=(job, photos, groups), daemon=True).start()
    return {"job_id": job_id, "total": len(photos)}


@app.get("/api/sort/{job_id}")
def sort_status(request: Request, job_id: str):
    job = _sorts.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown sort")
    _need_album(request, job["folder_id"])
    return {k: v for k, v in job.items() if k != "lock"}


# ------------------------------------------------------------- export -----
def _clean_name(name) -> str:
    return " ".join(str(name or "").split())[:100]


def _copy_with_retry(svc, file_id: str, folder_id: str):
    """Return None on success, or a short error string."""
    for attempt in range(4):
        try:
            gd.copy_into(svc, file_id, folder_id)
            return None
        except HttpError as e:
            busy = e.resp.status in (429, 500, 502, 503) or "ateLimit" in str(e)
            if busy and attempt < 3:
                time.sleep(1.5 * 2 ** attempt)
                continue
            return "HTTP %s" % e.resp.status
        except Exception as e:
            return str(e)[:120]


def _export_worker(job: dict, creds_data: dict, dest_link: str, dest_name: str):
    """Make one folder per person and copy that person's photos into it."""
    try:
        creds = gd.creds_from_session(creds_data)
        svc = gd.service(creds)
        fallback_name = "FaceFinder - %s" % (job["album"] or "album")

        given = None
        if dest_link:
            try:
                given = gd.folder_meta(svc, gd.parse_folder_id(dest_link))
            except Exception as e:
                raise RuntimeError(
                    "Cannot open the destination folder. Check the link, or leave "
                    "it empty to get a new folder in My Drive."
                ) from e
            root = given
        else:
            root = gd.ensure_folder(svc, dest_name or fallback_name)

        local = threading.local()   # Drive clients are not thread-safe
        tally = threading.Lock()

        with ThreadPoolExecutor(max_workers=config.COPY_WORKERS) as pool:
            for person in job["people"]:
                try:
                    folder = gd.ensure_folder(svc, person["name"], parent=root["id"])
                except HttpError:
                    if root is not given:
                        raise
                    # The app may only write where Drive lets it. Never lose the
                    # work: put the folders somewhere it can write and say so.
                    root = gd.ensure_folder(svc, fallback_name)
                    job["note"] = (
                        'FaceFinder is not allowed to write into "%s", so the '
                        'folders are in "%s" in your My Drive instead. You can '
                        "drag them across." % (given["name"], root["name"])
                    )
                    given = None
                    folder = gd.ensure_folder(svc, person["name"], parent=root["id"])

                job["root_name"] = root["name"]
                job["root_url"] = "https://drive.google.com/drive/folders/" + root["id"]
                person["url"] = "https://drive.google.com/drive/folders/" + folder["id"]

                have = gd.copied_sources(svc, folder["id"])
                todo = [f for f in person.pop("file_ids") if f not in have]
                person["skipped"] = person["total"] - len(todo)
                job["done"] += person["skipped"]
                job["skipped"] += person["skipped"]

                def one(file_id, folder_id=folder["id"]):
                    if not hasattr(local, "svc"):
                        local.svc = gd.service(creds)
                    err = _copy_with_retry(local.svc, file_id, folder_id)
                    with tally:
                        if err:
                            job["failed"].append({"file_id": file_id, "error": err})
                        else:
                            person["copied"] += 1
                            job["copied"] += 1
                        job["done"] += 1

                list(pool.map(one, todo))
        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)[:300]
    finally:
        job["finished"] = time.time()


@app.post("/api/export")
def export(request: Request, body: dict = Body(...)):
    """Start copying. groups: [{name, file_ids}], one Drive folder per name."""
    _creds(request)
    folder_id = body.get("folder_id")
    _need_album(request, folder_id)

    merged = {}                 # two groups with one name are one person
    for g in (body.get("groups") or [])[:300]:
        name = _clean_name(g.get("name"))
        ids = [f for f in (g.get("file_ids") or []) if isinstance(f, str)]
        if not name or not ids:
            continue
        slot = merged.setdefault(name.casefold(), {"name": name, "ids": {}})
        slot["ids"].update(dict.fromkeys(ids))
    if not merged:
        raise HTTPException(400, "Give at least one person a name and some photos")

    # Old finished jobs are only progress reports; drop them after an hour.
    for old in [k for k, j in _exports.items() if time.time() - j.get("finished", 9e18) > 3600]:
        _exports.pop(old, None)

    row = store.album(folder_id)
    people_rows = [
        {
            "name": s["name"],
            "file_ids": list(s["ids"]),
            "total": len(s["ids"]),
            "copied": 0,
            "skipped": 0,
            "url": None,
        }
        for s in merged.values()
    ]
    job = {
        "status": "running",
        "album": row["name"] if row else "",
        "total": sum(p["total"] for p in people_rows),
        "done": 0,
        "copied": 0,
        "skipped": 0,
        "failed": [],
        "people": people_rows,
        "root_name": None,
        "root_url": None,
        "note": None,
        "message": None,
    }
    job_id = secrets.token_urlsafe(12)
    _exports[job_id] = job
    threading.Thread(
        target=_export_worker,
        args=(
            job,
            request.session["creds"],
            (body.get("dest_link") or "").strip(),
            _clean_name(body.get("dest_name")),
        ),
        daemon=True,
    ).start()
    return {"job_id": job_id, "total": job["total"]}


@app.get("/api/export/{job_id}")
def export_status(job_id: str):
    job = _exports.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown export")
    out = {k: v for k, v in job.items() if k not in ("people", "failed")}
    out["failed"] = len(job["failed"])
    out["people"] = [
        {k: v for k, v in p.items() if k != "file_ids"} for p in job["people"]
    ]
    return out


# --------------------------------------------------------------- page -----
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
