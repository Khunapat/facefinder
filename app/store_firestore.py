"""The same cache as store.py, kept in Firestore instead of a SQLite file.

Cloud Run's disk is wiped whenever the instance restarts, so on Cloud Run the
index lives here and survives restarts and redeploys. Picked with
STORE=firestore (see config.py); the functions match store.py one for one.

Layout:
  albums/{folder_id}                     name, status, total, done, faces, message
  albums/{folder_id}/photos/{file_id}    name, w, h, dhash, judged, ai,
                                         faces: [{det_score, bbox, embedding}]

One document per photo, with its faces inside: a 512-d embedding is 2 KB, so
even a 100-face group photo stays far below Firestore's 1 MiB document limit,
and a scan costs one write per photo rather than one per face.
"""
import threading
import time

import numpy as np

from . import config

__all__ = [
    "album", "set_album", "bump_progress", "indexed_file_ids", "save_photo",
    "load_matrix", "save_ai", "photos", "unjudged", "judged_count",
    "clear_album", "face_box",
]

_lock = threading.Lock()
_db = None


def db():
    global _db
    with _lock:
        if _db is None:
            from google.cloud import firestore

            _db = firestore.Client(
                project=config.GOOGLE_CLOUD_PROJECT or None,
                database=config.FIRESTORE_DATABASE,
            )
        return _db


def _album_ref(folder_id: str):
    return db().collection("albums").document(folder_id)


def _photos(folder_id: str):
    return _album_ref(folder_id).collection("photos")


def album(folder_id: str):
    snap = _album_ref(folder_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict()
    out = {"folder_id": folder_id, "name": None, "status": "pending", "total": 0,
           "done": 0, "faces": 0, "message": None, "updated_at": None}
    out.update(d)
    return out


def set_album(folder_id: str, **fields):
    fields["updated_at"] = time.time()
    ref = _album_ref(folder_id)
    if not ref.get().exists:
        fields.setdefault("status", "pending")
        for k in ("total", "done", "faces"):
            fields.setdefault(k, 0)
    ref.set(fields, merge=True)


def bump_progress(folder_id: str, done_delta: int = 0, faces_delta: int = 0):
    from google.cloud import firestore

    _album_ref(folder_id).update({
        "done": firestore.Increment(done_delta),
        "faces": firestore.Increment(faces_delta),
        "updated_at": time.time(),
    })


def indexed_file_ids(folder_id: str) -> set:
    return {s.id for s in _photos(folder_id).select([]).stream()}


def save_photo(folder_id: str, file_id: str, name: str, faces: list, size=None, dhash=None):
    w, h = size if size else (None, None)
    rows = []
    for f in faces:
        emb = np.asarray(f["embedding"], dtype=np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        rows.append({
            "det_score": float(f.get("det_score", 0.0)),
            "bbox": [round(float(v), 1) for v in f.get("bbox", [])],
            "embedding": emb.tobytes(),
        })
    _photos(folder_id).document(file_id).set({
        "name": name, "w": w, "h": h, "dhash": dhash,
        "judged": False, "ai": None, "faces": rows,
    })


def load_matrix(folder_id: str):
    """Return (matrix [N,d] float32 L2-normalised, meta list) for one album."""
    vecs, meta = [], []
    for snap in _photos(folder_id).select(["name", "faces"]).stream():
        d = snap.to_dict()
        for i, f in enumerate(d.get("faces") or []):
            vecs.append(np.frombuffer(f["embedding"], dtype=np.float32))
            meta.append({
                "file_id": snap.id,
                "name": d.get("name"),
                "face_idx": i,
                "det_score": f.get("det_score", 0.0),
                "bbox": list(f.get("bbox") or []),
            })
    if not vecs:
        return np.zeros((0, 0), dtype=np.float32), []
    return np.stack(vecs), meta


def save_ai(folder_id: str, file_id: str, judgement: dict):
    _photos(folder_id).document(file_id).update({"ai": judgement, "judged": True})


def photos(folder_id: str) -> list:
    out = []
    for snap in _photos(folder_id).select(["name", "w", "h", "dhash", "ai"]).stream():
        d = snap.to_dict()
        out.append({
            "file_id": snap.id,
            "name": d.get("name"),
            "size": (d["w"], d["h"]) if d.get("w") else None,
            "dhash": d.get("dhash"),
            "ai": d.get("ai") or None,
        })
    return out


def unjudged(folder_id: str) -> list:
    from google.cloud.firestore_v1.base_query import FieldFilter

    q = _photos(folder_id).where(filter=FieldFilter("judged", "==", False)).select(["name"])
    return [{"id": s.id, "name": s.to_dict().get("name")} for s in q.stream()]


def judged_count(folder_id: str) -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter

    q = _photos(folder_id).where(filter=FieldFilter("judged", "==", True)).count()
    return int(q.get()[0][0].value)


def clear_album(folder_id: str):
    col = _photos(folder_id)
    while True:
        docs = list(col.select([]).limit(400).stream())
        if not docs:
            break
        batch = db().batch()
        for d in docs:
            batch.delete(d.reference)
        batch.commit()
    _album_ref(folder_id).delete()


def face_box(folder_id: str, file_id: str, face_idx: int):
    snap = _photos(folder_id).document(file_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict()
    faces = d.get("faces") or []
    if not 0 <= face_idx < len(faces):
        return None
    return list(faces[face_idx].get("bbox") or []), ((d["w"], d["h"]) if d.get("w") else None)
