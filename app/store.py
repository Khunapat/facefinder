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
"""


def conn() -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        c = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        # Added after the first release: the size each photo was scanned at.
        have = {r["name"] for r in c.execute("PRAGMA table_info(photos)")}
        for col in ("w", "h"):
            if col not in have:
                try:
                    c.execute(f"ALTER TABLE photos ADD COLUMN {col} INTEGER")
                except sqlite3.OperationalError:
                    pass                # another thread added it first
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


def save_photo(folder_id: str, file_id: str, name: str, faces: list, size=None):
    """faces: list of dicts with embedding (np.ndarray), det_score, bbox.
    size: (width, height) of the image the boxes were measured on."""
    c = conn()
    w, h = size if size else (None, None)
    c.execute(
        "INSERT OR REPLACE INTO photos (folder_id, file_id, name, w, h) "
        "VALUES (?,?,?,?,?)",
        (folder_id, file_id, name, w, h),
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
