"""The Gemini curation features through the real HTTP routes, with Google Drive
and Gemini both replaced by stand-ins (tests/fakedrive.py, tests/fakegemini.py).

Covers: the scan storing a judgement and a burst fingerprint for every photo,
culling (bursts, flaws, reasons), best shots for one person, suggesting groups,
sorting by description into the export, and that every new route still
requires the album to have been opened by this session.

What it cannot cover: how well the real Gemini judges photos. That needs a
Google Cloud project and is checked by hand.

Run:  python -m tests.test_gemini
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DATA_DIR", os.path.join(ROOT, "data"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "dev")
os.environ["GEMINI"] = "off"     # never the real Gemini here; the stand-in is switched in below

import cv2  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, main  # noqa: E402
from tests import fakedrive, fakegemini  # noqa: E402

TMP = tempfile.mkdtemp(prefix="facefinder-gemini-")
config.DB_PATH = os.path.join(TMP, "index.sqlite")

# The album: the sample photos, plus a near-copy of one (a burst) and a
# blurred copy of another (a reject).
ALBUM = os.path.join(TMP, "album")
shutil.copytree(os.path.join(ROOT, "tests", "img"), ALBUM)
img = cv2.imread(os.path.join(ALBUM, "obama.jpg"))
cv2.imwrite(os.path.join(ALBUM, "obama-b.jpg"), cv2.convertScaleAbs(img, alpha=1.03, beta=2))
img = cv2.imread(os.path.join(ALBUM, "biden.jpg"))
cv2.imwrite(os.path.join(ALBUM, "zz_blur.jpg"), cv2.GaussianBlur(img, (0, 0), 9))

drive = fakedrive.install(os.path.join(TMP, "drive"), image_dirs=[ALBUM])
checks = []


def check(label, passed, detail=""):
    checks.append(passed)
    print(("  PASS  " if passed else "  FAIL  ") + label + (("   " + str(detail)) if detail and not passed else ""))


def wait(fn, done, seconds=240):
    end = time.time() + seconds
    while time.time() < end:
        value = fn()
        if done(value):
            return value
        time.sleep(0.3)
    raise TimeoutError(str(value))


def main_test():
    c = TestClient(main.app)
    c.get("/dev/login", follow_redirects=False)
    fid = fakedrive.ALBUM_ID

    print("Gemini switched off")
    check("/api/me says Gemini is off", c.get("/api/me").json()["gemini"] is False)

    fakegemini.install()
    print("Before opening the album")
    for path in ("/api/cull", "/api/best", "/api/groups/suggest", "/api/sort"):
        r = c.post(path, json={"folder_id": fid, "file_ids": ["x"], "groups": [{"name": "a"}]})
        check("%s refuses an album this session has not opened" % path, r.status_code == 403, r.status_code)

    print("Scanning")
    c.post("/api/album", json={"folder": fakedrive.ALBUM_URL})
    c.post("/api/index", json={"folder_id": fid})
    st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    check("scan finished", st["status"] == "ready", st)
    check("every photo was judged", st["judged"] == st["done"] == 7, (st["judged"], st["done"]))

    print("Cull")
    r = c.post("/api/cull", json={"folder_id": fid}).json()
    rejected = {x["name"]: x for x in r["reject"]}
    review = {x["name"]: x for x in r["review"]}
    kept = {x["name"] for x in r["keep"]}
    check("the near-copy and the original are one burst", r["bursts"] == 1, r["bursts"])
    check("only one frame of the burst is kept", len({"obama.jpg", "obama-b.jpg"} & kept) == 1, kept)
    burst_loser = ({"obama.jpg", "obama-b.jpg"} - kept).pop()
    check("the other, a near-identical copy, is rejected as the weaker frame",
          "better frame" in rejected.get(burst_loser, {}).get("reason", ""), rejected.get(burst_loser))
    check("the blurred photo is rejected for being blurry",
          "Blurry" in rejected.get("zz_blur.jpg", {}).get("reason", ""), rejected.get("zz_blur.jpg"))
    check("every photo is in exactly one pile", len(kept) + len(review) + len(rejected) == 7)
    check("every decision has a reason", all(x.get("reason") for x in r["keep"] + r["review"] + r["reject"]))
    gentle = c.post("/api/cull", json={"folder_id": fid, "strictness": "gentle"}).json()
    check("gentle does not reject the blurred photo", "zz_blur.jpg" not in {x["name"] for x in gentle["reject"]})

    print("Cull rules, without Drive or Gemini")
    from app import curate
    ph = lambda name, keeper, flaws=(), dh="0000000000000000", unsure=False: {
        "file_id": name, "name": name, "dhash": dh,
        "ai": None if keeper is None else {"keeper": keeper, "flaws": list(flaws), "reason": "r", "unsure": unsure}}
    res = curate.cull([ph("a", 7, ["eyes_closed"], "ffffffffffffffff"), ph("b", None, dh="0f0f0f0f0f0f0f0f"),
                       ph("c", 8, unsure=True, dh="00000000ffffffff"), ph("d", 2, ["blurry"], "ffff0000ffff0000")])
    piles = {x["file_id"]: k for k in ("keep", "review", "reject") for x in res[k]}
    check("a well-scored frame with closed eyes goes to review, not reject", piles.get("a") == "review", piles)
    check("a photo Gemini could not check goes to review", piles.get("b") == "review", piles)
    check("a photo Gemini was unsure about goes to review", piles.get("c") == "review", piles)
    check("a low-scored blurry frame is rejected", piles.get("d") == "reject", piles)
    near = curate.cull([ph("x1", 8, dh="0000000000000000"), ph("x2", 7, dh="00000000000001ff")])
    check("a similar but different frame of a burst goes to review",
          [x["file_id"] for x in near["review"]] == ["x2"], near)
    picks = curate.best_shots(["p%d" % i for i in range(6)],
                              {"p%d" % i: {"keeper": 9, "flaws": [], "reason": "r", "scene": "stage"} for i in range(6)},
                              {}, 3, {"p%d" % i: ("0" * 16 if i < 4 else "f" * 16) for i in range(6)})
    ids = [p["file_id"] for p in picks]
    check("best shots mix different-looking photos instead of near-copies",
          any(i in ids for i in ("p4", "p5")) and any(i in ids for i in ("p0", "p1", "p2", "p3")), ids)

    print("Best shots")
    people = c.post("/api/people", json={"folder_id": fid}).json()["people"]
    biden = next(p for p in people if any(x["file_id"] == "biden.jpg" for x in p["photos"]))
    ids = [x["file_id"] for x in biden["photos"]]
    r = c.post("/api/best", json={"folder_id": fid, "file_ids": ids, "n": 2}).json()
    names = [b["name"] for b in r["best"]]
    check("best shots come from that person's photos", set(names) <= set(ids), names)
    check("the blurred photo is not the best shot", names[0] != "zz_blur.jpg", names)
    check("each best shot has a reason", all(b["reason"] for b in r["best"]))

    print("Sort by description")
    sug = c.post("/api/groups/suggest", json={"folder_id": fid}).json()["groups"]
    check("Gemini suggests at least one group", len(sug) >= 1, sug)
    job = c.post("/api/sort", json={"folder_id": fid, "groups": sug}).json()
    res = wait(lambda: c.get("/api/sort/" + job["job_id"]).json(), lambda j: j["status"] != "running")
    placed = {f for g in res["groups"] for f in g["file_ids"]} | set(res["check"]) | set(res["none"])
    check("sorting finished", res["status"] == "done", res.get("message"))
    check("every photo was placed somewhere", len(placed) == 7, placed)
    check("at least one group has photos", any(g["file_ids"] for g in res["groups"]))
    other = TestClient(main.app)
    other.get("/dev/login", follow_redirects=False)
    check("another session cannot read the result", other.get("/api/sort/" + job["job_id"]).status_code == 403)

    groups = [{"name": g["name"], "file_ids": g["file_ids"]} for g in res["groups"] if g["file_ids"]]
    r = c.post("/api/export", json={"folder_id": fid, "groups": groups}).json()
    exp = wait(lambda: c.get("/api/export/" + r["job_id"]).json(), lambda j: j["status"] != "running")
    tree = drive.tree()
    check("each group became a Drive folder with its photos",
          all(sorted(g["file_ids"]) == tree.get("%s/%s" % (exp["root_name"], g["name"])) for g in groups),
          (groups, tree))

    print()
    print("%d of %d checks passed" % (sum(checks), len(checks)))
    return all(checks)


if __name__ == "__main__":
    sys.exit(0 if main_test() else 1)
