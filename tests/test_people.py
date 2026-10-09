"""End-to-end check of the multi-person flow through the real HTTP routes, with
Google Drive replaced by local folders (tests/fakedrive.py).

Covers: grouping an album into people, searching for a named person, and
exporting one folder per name, including re-running and a locked destination.

Run:  python -m tests.test_people
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Reuse the downloaded face model, but keep the index in a throwaway database.
os.environ.setdefault("DATA_DIR", os.path.join(ROOT, "data"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "dev")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, main  # noqa: E402
from tests import fakedrive  # noqa: E402

TMP = tempfile.mkdtemp(prefix="facefinder-people-")
config.DB_PATH = os.path.join(TMP, "index.sqlite")
IMG = os.path.join(ROOT, "tests", "img")
drive = fakedrive.install(os.path.join(TMP, "drive"), image_dirs=[IMG])

OBAMA = ["obama.jpg", "obama2.jpg", "obama_small.jpg", "two_people.jpg"]
BIDEN = ["biden.jpg", "two_people.jpg"]
checks = []


def check(label, passed, detail=""):
    checks.append(passed)
    print(("  PASS  " if passed else "  FAIL  ") + label + (("   " + str(detail)) if detail and not passed else ""))


def wait(fn, done, seconds=180):
    end = time.time() + seconds
    while time.time() < end:
        value = fn()
        if done(value):
            return value
        time.sleep(0.3)
    raise TimeoutError(str(value))


def run_export(client, **body):
    r = client.post("/api/export", json={"folder_id": fakedrive.ALBUM_ID, **body})
    if r.status_code != 200:
        return r
    job_id = r.json()["job_id"]
    return wait(lambda: client.get("/api/export/" + job_id).json(),
                lambda j: j["status"] != "running")


def main_test():
    c = TestClient(main.app)

    # --- access control ---
    check("search refused when signed out",
          c.post("/api/people", json={"folder_id": fakedrive.ALBUM_ID}).status_code == 401)
    c.get("/dev/login")
    check("album data refused until this session opened the album",
          c.post("/api/people", json={"folder_id": fakedrive.ALBUM_ID}).status_code == 403)

    # --- open and scan ---
    a = c.post("/api/album", json={"folder": fakedrive.ALBUM_URL}).json()
    check("album opens from a pasted link", a.get("folder_id") == fakedrive.ALBUM_ID, a)
    c.post("/api/index", json={"folder_id": fakedrive.ALBUM_ID})
    st = wait(lambda: c.get("/api/album/%s/status" % fakedrive.ALBUM_ID).json(),
              lambda s: s["status"] in ("ready", "error"))
    check("scan finishes: 5 photos, 6 faces",
          (st["status"], st["done"], st["faces"]) == ("ready", 5, 6), st)

    # --- everyone in the album ---
    r = c.post("/api/people", json={"folder_id": fakedrive.ALBUM_ID, "grouping": "balanced"}).json()
    groups = [sorted(p["name"] for p in person["photos"]) for person in r["people"]]
    print("\n  people found:", [(len(g), g) for g in groups], "\n")
    check("album splits into exactly 2 people", len(groups) == 2, groups)
    check("biggest group is the 4 photos of person A", groups and groups[0] == sorted(OBAMA), groups)
    check("second group is the 2 photos of person B", len(groups) > 1 and groups[1] == sorted(BIDEN), groups)
    check("the group photo is filed under both people",
          all("two_people.jpg" in g for g in groups))

    cover = r["people"][0]["cover"]
    f = c.get("/api/face/%s/%s/%d" % (fakedrive.ALBUM_ID, cover["file_id"], cover["face_idx"]))
    crop = cv2.imdecode(np.frombuffer(f.content, np.uint8), cv2.IMREAD_COLOR) if f.status_code == 200 else None
    check("face crop for naming is a 192px square JPEG",
          crop is not None and crop.shape[:2] == (192, 192), f.status_code)

    # --- a named person from an uploaded photo ---
    with open(os.path.join(IMG, "obama.jpg"), "rb") as fh:
        s = c.post("/api/search", data={"folder_id": fakedrive.ALBUM_ID, "threshold": "0.20"},
                   files=[("selfies", ("me.jpg", fh.read(), "image/jpeg"))]).json()
    hits = {m["file_id"]: m["score"] for m in s["matches"]}
    check("search by uploaded photo finds all 4 of that person",
          all(hits.get(n, 0) >= 0.38 for n in OBAMA), hits)
    check("the other person stays below the default strictness",
          hits.get("biden.jpg", 0) < 0.38, hits)
    check("grid thumbnail route answers",
          c.get("/api/thumb/obama.jpg?s=400").status_code == 200)

    # --- one folder per name ---
    job = run_export(c, dest_name="Class of 2026", groups=[
        {"name": "Barack", "file_ids": OBAMA},
        {"name": "Joe", "file_ids": BIDEN},
        {"name": "  barack ", "file_ids": ["biden.jpg"]},    # same name twice: one folder
    ])
    tree = drive.tree()
    print("\n  folders written:", tree, "\n")
    check("export finishes without failures",
          (job["status"], job["failed"]) == ("done", 0), job)
    check("two names typed the same way share one folder",
          tree.get("Class of 2026/Barack") == sorted(OBAMA + ["biden.jpg"]), tree)
    check("each person gets their own folder",
          tree.get("Class of 2026/Joe") == sorted(BIDEN), tree)
    check("every person row links to its folder",
          all(p["url"] for p in job["people"]) and job["root_name"] == "Class of 2026", job)

    calls = drive.copy_calls
    again = run_export(c, dest_name="Class of 2026", groups=[
        {"name": "Barack", "file_ids": OBAMA}, {"name": "Joe", "file_ids": BIDEN}])
    check("running it again copies nothing twice",
          drive.copy_calls == calls and again["skipped"] == 6 and again["copied"] == 0, again)

    locked = run_export(c, dest_link=fakedrive.LOCKED_URL,
                        groups=[{"name": "Joe", "file_ids": BIDEN}])
    check("a destination that refuses writes falls back, and says so",
          locked["status"] == "done" and locked["copied"] == 2 and bool(locked["note"])
          and locked["root_name"].startswith("FaceFinder - "), locked)

    bad = run_export(c, groups=[{"name": "   ", "file_ids": OBAMA}])
    check("export with no usable name is rejected", getattr(bad, "status_code", 200) == 400)

    print()
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main_test())
