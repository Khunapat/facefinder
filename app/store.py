"""SQLite cache of face embeddings, keyed by Drive folder.

The whole point of this table: a graduation album gets indexed ONCE, then every
classmate who searches it gets an answer in well under a second.
"""
import json
import sqlite3
import threading
import time

import numpy as np

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS albums (
    folder_id   TEXT PRIMARY KEY,
    name        TEXT,
    status      TEXT NOT NULL,           -- pending | indexing | ready | error
    total       INTEGER DEFAULT 0,
    done        INTEGER DEFAULT 0,
    faces       INTEGER DEFAULT 0,
    message     TEXT,
    updated_at  REAL
);
CREATE TABLE IF NOT EXISTS photos (
    folder_id   TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    name        TEXT,
    PRIMARY KEY (folder_id, file_id)
);
CREATE TABLE IF NOT EXISTS faces (
    folder_id   TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    face_idx    INTEGER NOT NULL,
    det_score   REAL,
    bbox        TEXT,
    embedding   BLOB NOT NULL,           -- float32, L2-normalised
    PRIMARY KEY (folder_id, file_id, face_idx)
);
CREATE INDEX IF NOT EXISTS faces_folder ON faces(folder_id);
CREATE TABLE IF NOT EXISTS ai_cache (        -- Gemini's judgement of one photo, kept
    key         TEXT PRIMARY KEY,            -- through rescans: Drive id + checksum
    ai          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS names (           -- the names a user gave people in an album
    user        TEXT NOT NULL,
    folder_id   TEXT NOT NULL,
    data        TEXT NOT NULL,               -- JSON [{name, files:[file_id, ...]}]
    PRIMARY KEY (user, folder_id)
);
CREATE TABLE IF NOT EXISTS recent (          -- the albums each user opened
    user        TEXT NOT NULL,               -- a hash of the account's email
    folder_id   TEXT NOT NULL,
    opened_at   REAL,
    PRIMARY KEY (user, folder_id)
);
"""


def conn() -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        c = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        # Added after the first release: the size each photo was scanned at,
        # its burst fingerprint, and Gemini's judgement as JSON.
        have = {r["name"] for r in c.execute("PRAGMA table_info(photos)")}
        for col, kind in (("w", "INTEGER"), ("h", "INTEGER"), ("dhash", "TEXT"), ("ai", "TEXT")):
            if col not in have:
                try:
                    c.execute(f"ALTER TABLE photos ADD COLUMN {col} {kind}")
                except sqlite3.OperationalError:
                    pass                # another thread added it first
        # Which photos the user chose to scan (JSON list), NULL for the whole album.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(albums)")}
        for col, kind in (("scope", "TEXT"), ("album_total", "INTEGER")):
            if col not in cols:      # album_total: photos in the album, scope or not
                try:
                    c.execute(f"ALTER TABLE albums ADD COLUMN {col} {kind}")
                except sqlite3.OperationalError:
                    pass
        c.commit()
        _local.conn = c
    return _local.conn


def album(folder_id: str):
    return conn().execute(
        "SELECT * FROM albums WHERE folder_id=?", (folder_id,)
    ).fetchone()


def set_album(folder_id: str, **fields):
    fields["updated_at"] = time.time()
    c = conn()
    if album(folder_id) is None:
        fields.setdefault("status", "pending")
        cols = ", ".join(["folder_id"] + list(fields))
        marks = ", ".join("?" * (len(fields) + 1))
        c.execute(
            f"INSERT INTO albums ({cols}) VALUES ({marks})",
            [folder_id] + list(fields.values()),
        )
    else:
        sets = ", ".join(f"{k}=?" for k in fields)
        c.execute(
            f"UPDATE albums SET {sets} WHERE folder_id=?",
            list(fields.values()) + [folder_id],
        )
    c.commit()


def bump_progress(folder_id: str, done_delta: int = 0, faces_delta: int = 0):
    c = conn()
    c.execute(
        "UPDATE albums SET done=done+?, faces=faces+?, updated_at=? WHERE folder_id=?",
        (done_delta, faces_delta, time.time(), folder_id),
    )
    c.commit()


def indexed_file_ids(folder_id: str) -> set:
    rows = conn().execute(
        "SELECT file_id FROM photos WHERE folder_id=?", (folder_id,)
    ).fetchall()
    return {r["file_id"] for r in rows}


def save_photo(folder_id: str, file_id: str, name: str, faces: list, size=None, dhash=None):
    """faces: list of dicts with embedding (np.ndarray), det_score, bbox.
    size: (width, height) of the image the boxes were measured on.
    dhash: the photo's burst fingerprint (curate.dhash)."""
    c = conn()
    w, h = size if size else (None, None)
    c.execute(
        "INSERT OR REPLACE INTO photos (folder_id, file_id, name, w, h, dhash) "
        "VALUES (?,?,?,?,?,?)",
        (folder_id, file_id, name, w, h, dhash),
    )
    for i, f in enumerate(faces):
        emb = np.asarray(f["embedding"], dtype=np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        c.execute(
            "INSERT OR REPLACE INTO faces "
            "(folder_id, file_id, face_idx, det_score, bbox, embedding) "
            "VALUES (?,?,?,?,?,?)",
            (
                folder_id,
                file_id,
                i,
                float(f.get("det_score", 0.0)),
                json.dumps([round(float(v), 1) for v in f.get("bbox", [])]),
                emb.tobytes(),
            ),
        )
    c.commit()


def load_matrix(folder_id: str):
    """Return (matrix [N,512] float32 L2-normalised, meta list) for one album."""
    rows = conn().execute(
        "SELECT f.file_id, f.face_idx, f.det_score, f.bbox, f.embedding, p.name "
        "FROM faces f JOIN photos p ON p.folder_id=f.folder_id AND p.file_id=f.file_id "
        "WHERE f.folder_id=?",
        (folder_id,),
    ).fetchall()
    if not rows:
        return np.zeros((0, 0), dtype=np.float32), []
    mat = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    meta = [
        {
            "file_id": r["file_id"],
            "name": r["name"],
            "face_idx": r["face_idx"],
            "det_score": r["det_score"],
            "bbox": json.loads(r["bbox"] or "[]"),
        }
        for r in rows
    ]
    return mat, meta


def save_ai(folder_id: str, file_id: str, judgement: dict):
    c = conn()
    c.execute(
        "UPDATE photos SET ai=? WHERE folder_id=? AND file_id=?",
        (json.dumps(judgement, ensure_ascii=False), folder_id, file_id),
    )
    c.commit()


def cache_ai(key: str, judgement: dict):
    """Keep Gemini's judgement of a photo apart from the album, so a rescan
    (which clears the album) does not pay Gemini again for the same photo."""
    c = conn()
    c.execute("INSERT OR REPLACE INTO ai_cache (key, ai) VALUES (?,?)",
              (key, json.dumps(judgement, ensure_ascii=False)))
    c.commit()


def forget_ai(file_ids):
    c = conn()
    for f in file_ids:
        c.execute("DELETE FROM ai_cache WHERE substr(key, 1, ?) = ?", (len(f) + 1, f + ":"))
    c.commit()


def cached_ai(key: str):
    r = conn().execute("SELECT ai FROM ai_cache WHERE key=?", (key,)).fetchone()
    return json.loads(r["ai"]) if r else None


def photos(folder_id: str) -> list:
    """Every scanned photo with its fingerprint and Gemini judgement (or None)."""
    rows = conn().execute(
        "SELECT file_id, name, w, h, dhash, ai FROM photos WHERE folder_id=?",
        (folder_id,),
    ).fetchall()
    return [
        {
            "file_id": r["file_id"],
            "name": r["name"],
            "size": (r["w"], r["h"]) if r["w"] else None,
            "dhash": r["dhash"],
            "ai": json.loads(r["ai"]) if r["ai"] else None,
        }
        for r in rows
    ]


def photo_ai(folder_id: str, file_id: str):
    r = conn().execute("SELECT name, ai FROM photos WHERE folder_id=? AND file_id=?",
                       (folder_id, file_id)).fetchone()
    if r is None:
        return None
    return {"name": r["name"], "ai": json.loads(r["ai"]) if r["ai"] else None}


def unjudged(folder_id: str) -> list:
    """Photos Gemini has not checked yet: [{id, name}], ready for list_images-style use."""
    rows = conn().execute(
        "SELECT file_id, name FROM photos WHERE folder_id=? AND ai IS NULL",
        (folder_id,),
    ).fetchall()
    return [{"id": r["file_id"], "name": r["name"]} for r in rows]


def judged_count(folder_id: str) -> int:
    return conn().execute(
        "SELECT COUNT(*) FROM photos WHERE folder_id=? AND ai IS NOT NULL", (folder_id,)
    ).fetchone()[0]


def clear_album(folder_id: str):
    c = conn()
    c.execute("DELETE FROM faces WHERE folder_id=?", (folder_id,))
    c.execute("DELETE FROM photos WHERE folder_id=?", (folder_id,))
    c.execute("DELETE FROM albums WHERE folder_id=?", (folder_id,))
    c.commit()


def face_box(folder_id: str, file_id: str, face_idx: int):
    """Return (bbox, (w, h) or None) for one stored face, or None if unknown."""
    r = conn().execute(
        "SELECT f.bbox, p.w, p.h FROM faces f "
        "JOIN photos p ON p.folder_id=f.folder_id AND p.file_id=f.file_id "
        "WHERE f.folder_id=? AND f.file_id=? AND f.face_idx=?",
        (folder_id, file_id, face_idx),
    ).fetchone()
    if r is None:
        return None
    return json.loads(r["bbox"] or "[]"), ((r["w"], r["h"]) if r["w"] else None)


def save_names(user: str, folder_id: str, people: list):
    c = conn()
    c.execute("INSERT OR REPLACE INTO names (user, folder_id, data) VALUES (?,?,?)",
              (user, folder_id, json.dumps(people, ensure_ascii=False)))
    c.commit()


def load_names(user: str, folder_id: str) -> list:
    r = conn().execute("SELECT data FROM names WHERE user=? AND folder_id=?", (user, folder_id)).fetchone()
    return json.loads(r["data"]) if r else []


def remember_album(user: str, folder_id: str):
    c = conn()
    c.execute("INSERT OR REPLACE INTO recent (user, folder_id, opened_at) VALUES (?, ?, ?)",
              (user, folder_id, time.time()))
    c.commit()


def recent_albums(user: str, limit: int = 6) -> list:
    rows = conn().execute(
        "SELECT folder_id, opened_at FROM recent WHERE user=? ORDER BY opened_at DESC LIMIT ?",
        (user, limit)).fetchall()
    return [(r["folder_id"], r["opened_at"]) for r in rows]


def forget_album(user: str, folder_id: str):
    c = conn()
    c.execute("DELETE FROM recent WHERE user=? AND folder_id=?", (user, folder_id))
    c.commit()


def cover_ids(folder_id: str, n: int = 3) -> list:
    """A few photos to show for an album, ones with faces first."""
    rows = conn().execute(
        "SELECT p.file_id FROM photos p WHERE p.folder_id=? ORDER BY "
        "EXISTS(SELECT 1 FROM faces f WHERE f.folder_id=p.folder_id AND f.file_id=p.file_id) DESC, p.name LIMIT ?",
        (folder_id, n)).fetchall()
    return [r["file_id"] for r in rows]


# On Cloud Run the index lives in Firestore; every function above is replaced
# by its Firestore twin, so callers keep using store.<name> unchanged.
if config.STORE == "firestore":
    from . import store_firestore as _fs

    for _name in _fs.__all__:
        globals()[_name] = getattr(_fs, _name)
