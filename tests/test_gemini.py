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

fakedrive_real_list = main.gd.list_images     # the real one, before the stand-in replaces it
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
    check("the other, scored about the same, goes to review to compare",
          "Looks like" in review.get(burst_loser, {}).get("reason", ""), review.get(burst_loser))
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
    copy = curate.cull([ph("y1", 8, dh="0000000000000000"), ph("y2", 5, dh="0000000000000003")])
    check("a near-identical, clearly weaker copy of a kept frame is rejected",
          [x["file_id"] for x in copy["reject"]] == ["y2"] and "better copy" in copy["reject"][0]["reason"], copy)
    weak = curate.cull([ph("z1", 5, dh="0000000000000000"), ph("z2", 3, dh="0000000000000003")])
    check("a copy is not rejected when the better frame is itself only in review",
          not weak["reject"], weak)
    mixed = curate.cull([ph("u1", None, dh="0000000000000000"), ph("u2", 9, dh="0000000000000001", unsure=True),
                         ph("u3", 6, dh="0000000000000003")])
    check("unchecked and unsure frames in a burst go to review, never reject",
          {x["file_id"] for x in mixed["review"]} >= {"u1", "u2"} and not mixed["reject"], mixed)
    picks = curate.best_shots(["p%d" % i for i in range(6)],
                              {"p%d" % i: {"keeper": 9, "flaws": [], "reason": "r", "scene": "stage"} for i in range(6)},
                              {}, 3, {"p%d" % i: ("0" * 16 if i < 4 else "f" * 16) for i in range(6)})
    ids = [p["file_id"] for p in picks]
    check("best shots mix different-looking photos instead of near-copies",
          any(i in ids for i in ("p4", "p5")) and any(i in ids for i in ("p0", "p1", "p2", "p3")), ids)

    weakest = curate.best_shots(["w1", "w2", "w3", "w4"],
                                {"w1": {"keeper": 2, "flaws": ["blurry"], "reason": "r", "scene": "s"},
                                 "w2": {"keeper": 9, "flaws": [], "reason": "r", "scene": "s", "unsure": True},
                                 "w3": {"keeper": 3, "flaws": [], "reason": "r", "scene": "s"}},
                                {}, 10)
    check("Best 10 never picks a weak, unsure or unchecked photo, even as the first pick",
          weakest == [], weakest)
    good = curate.best_shots(["g1", "g2"], {"g1": {"keeper": 8, "flaws": [], "reason": "r", "scene": "s"}}, {}, 10)
    check("Best 10 returns fewer than 10 rather than pad the list", [p["file_id"] for p in good] == ["g1"], good)

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
    check("another session cannot read the result", other.get("/api/sort/" + job["job_id"]).status_code in (403, 404))

    groups = [{"name": g["name"], "file_ids": g["file_ids"]} for g in res["groups"] if g["file_ids"]]
    r = c.post("/api/export", json={"folder_id": fid, "groups": groups}).json()
    exp = wait(lambda: c.get("/api/export/" + r["job_id"]).json(), lambda j: j["status"] != "running")
    tree = drive.tree()
    check("each group became a Drive folder with its photos",
          all(sorted(g["file_ids"]) == tree.get("%s/%s" % (exp["root_name"], g["name"])) for g in groups),
          (groups, tree))

    print("Photo notes")
    note = c.get("/api/photo/%s/%s" % (fid, "biden.jpg")).json()
    check("a photo's saved Gemini note can be read for the preview", bool(note.get("description")), note)
    check("another session cannot read the notes", other.get("/api/photo/%s/biden.jpg" % fid).status_code == 403)
    cr = c.post("/api/cull", json={"folder_id": fid}).json()
    alike = [x for x in cr["review"] + cr["reject"] if x.get("similar_to")]
    check("a look-alike names the photo it looks like", alike and all(x.get("similar_name") for x in alike), cr["review"])
    best = c.post("/api/best", json={"folder_id": fid, "file_ids": [x["file_id"] for x in biden["photos"]]}).json()["best"]
    check("Best 10 picks carry Gemini's description as well as the reason", all("description" in b for b in best), best)

    print("Recent albums")
    rec = c.get("/api/albums/recent").json()["albums"]
    mine = next((a for a in rec if a["folder_id"] == fid), None)
    check("an opened album is on the account's recent list", mine is not None, rec)
    check("it carries its name, status and a few photos to show",
          mine and mine["name"] and mine["status"] == "ready" and 1 <= len(mine["covers"]) <= 3, mine)
    c.post("/api/albums/forget", json={"folder_id": fid})
    check("an album can be taken off the list", all(a["folder_id"] != fid for a in c.get("/api/albums/recent").json()["albums"]))
    c.post("/api/album", json={"folder": fakedrive.ALBUM_URL})
    check("opening it again puts it back", any(a["folder_id"] == fid for a in c.get("/api/albums/recent").json()["albums"]))
    check("signed out, there is no list", TestClient(main.app).get("/api/albums/recent").status_code == 401)

    print("Rescans and restarts")
    calls = []
    real_judge = main.gemini.judge

    def counted(jpeg):
        calls.append(1)
        return real_judge(jpeg)
    main.gemini.judge = counted
    try:
        c.post("/api/index", json={"folder_id": fid, "rebuild": True})
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    finally:
        main.gemini.judge = real_judge
    check("a rescan from the start keeps Gemini's notes and pays for none again",
          not calls and st["judged"] == st["done"] == 7, (len(calls), st.get("judged"), st.get("done")))
    main.store.set_album(fid, status="indexing")
    check("a scan that is still alive is not called stopped",
          c.get("/api/album/%s/status" % fid).json()["status"] == "indexing")
    main.store.conn().execute("UPDATE albums SET updated_at=? WHERE folder_id=?", (time.time() - 300, fid))
    main.store.conn().commit()
    st = c.get("/api/album/%s/status" % fid).json()
    check("a scan left behind by a restarted server shows as stopped, ready to resume",
          st["status"] == "stopped" and "interrupted" in st["message"], st)
    main.store.set_album(fid, status="ready")
    r = c.get("/api/export/no-such-job")
    check("a lost export says how to finish it", r.status_code == 404 and "Export again" in r.json()["detail"], r.text)

    print("Stop does not wait for Gemini")
    main.store.conn().execute("DELETE FROM ai_cache")
    main.store.conn().commit()

    def stuck(jpeg):
        time.sleep(25)          # a Gemini call that hangs
        return real_judge(jpeg)
    main.gemini.judge = stuck
    try:
        c.post("/api/index", json={"folder_id": fid, "rebuild": True})
        wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] == "indexing" and s["done"] >= 3)
        t0 = time.time()
        c.post("/api/index/stop", json={"folder_id": fid})
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] not in ("indexing", "pending"), 60)
        took = time.time() - t0
    finally:
        main.gemini.judge = real_judge
    check("Stop ends the scan within seconds even while Gemini calls hang",
          took < 8 and st["status"] in ("stopped", "ready"), (round(took, 1), st["status"]))
    c.post("/api/index", json={"folder_id": fid})
    st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    check("resuming afterwards finishes the album", st["status"] == "ready" and st["done"] == 7, st)

    print("Names kept for the account")
    r = c.post("/api/album/%s/names" % fid, json={"people": [
        {"name": " Mint ", "files": ["obama.jpg", "obama2.jpg"]}, {"name": "", "files": ["biden.jpg"]}]})
    got = c.get("/api/album/%s/names" % fid).json()["people"]
    check("names are saved with their photos, blanks dropped",
          r.json().get("saved") and got == [{"name": "Mint", "files": ["obama.jpg", "obama2.jpg"]}], got)
    check("another session cannot read them", other.get("/api/album/%s/names" % fid).status_code == 403)

    print("Folders this account cannot open")
    r = c.post("/api/album", json={"folder": "https://drive.google.com/drive/folders/private-folder-00000000000000"})
    d = r.json().get("detail") or {}
    check("a private folder is refused with a reason the page can explain",
          r.status_code == 403 and isinstance(d, dict) and d.get("code") == "no_access"
          and d.get("folder_id") == "private-folder-00000000000000" and "email" in d, r.text)
    r = c.post("/api/album", json={"folder": "https://drive.google.com/drive/folders/drive-down-000000000000000"})
    check("Drive not answering is not mistaken for no access", r.status_code == 503 and "Try again" in r.json()["detail"], r.text)

    print("Access and retries")
    r = c.post("/api/export", json={"folder_id": fid, "groups": [{"name": "x", "file_ids": ["not-in-album"]}]})
    check("export refuses photos from outside the album", r.status_code == 400, r.status_code)
    check("another session cannot read an export", other.get("/api/export/" + exp["job_id"] if "job_id" in exp
                                                             else "/api/export/x").status_code in (403, 404))
    check("album status needs an opened album", other.get("/api/album/%s/status" % fid).status_code == 403)

    real_fetch = main.gd.fetch_image_bytes

    def flaky(creds, svc, meta, size=None):
        if meta["name"] == "biden.jpg":
            raise OSError("network dropped")
        return real_fetch(creds, svc, meta, size)
    main.gd.fetch_image_bytes = flaky
    try:
        c.post("/api/index", json={"folder_id": fid, "rebuild": True})
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    finally:
        main.gd.fetch_image_bytes = real_fetch
    check("a photo that could not be read is not counted as done",
          st["done"] == st["total"] - 1 and "could not be read" in st["message"], st)
    c.post("/api/index", json={"folder_id": fid})
    st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    check("scanning again picks it up", st["done"] == st["total"] == 7, st)
    check("a rescan keeps the album's name", bool(st.get("name")), st)

    print("Stop and resume")
    import time as _time

    def slow(creds, svc, meta, size=None):
        _time.sleep(0.4)
        return real_fetch(creds, svc, meta, size)
    main.gd.fetch_image_bytes = slow
    try:
        c.post("/api/index", json={"folder_id": fid, "rebuild": True})
        _time.sleep(0.6)
        r = c.post("/api/index/stop", json={"folder_id": fid}).json()
        check("a running scan can be stopped", r.get("stopping") is True, r)
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] != "indexing" and s["status"] != "pending")
    finally:
        main.gd.fetch_image_bytes = real_fetch
    check("it ends as stopped, keeping what it scanned", st["status"] == "stopped" and st["done"] < st["total"], st)
    check("stopping when nothing runs is harmless",
          c.post("/api/index/stop", json={"folder_id": fid}).json().get("stopping") is False)
    check("another session cannot stop a scan", other.post("/api/index/stop", json={"folder_id": fid}).status_code == 403)
    c.post("/api/index", json={"folder_id": fid})
    st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    check("resuming finishes the album", st["status"] == "ready" and st["done"] == st["total"] == 7, st)

    print("Choose which photos to scan")
    files = c.get("/api/album/%s/files" % fid).json()["files"]
    check("the album's photos are listed with when they were taken",
          len(files) == 7 and all(f["taken"] for f in files) and all(f["scanned"] for f in files), files[:2])
    check("listed oldest first", [f["taken"] for f in files] == sorted(f["taken"] for f in files))
    check("another session cannot list them", other.get("/api/album/%s/files" % fid).status_code == 403)
    first3 = [f["id"] for f in files[:3]]
    ready = lambda: wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error", "stopped"))
    c.post("/api/index", json={"folder_id": fid, "rebuild": True, "file_ids": first3})
    st = ready()
    check("a scan of three chosen photos checks only those three", st["status"] == "ready" and st["total"] == st["done"] == 3, st)
    check("cull works on just those", len(sum((c.post("/api/cull", json={"folder_id": fid}).json()[k] for k in ("keep", "review", "reject")), [])) == 3)
    c.post("/api/index", json={"folder_id": fid})
    st = ready()
    check("scanning again without a choice keeps the same three", st["total"] == 3, st)
    c.post("/api/index", json={"folder_id": fid, "file_ids": [files[5]["id"]]})
    st = ready()
    check("choosing one more adds it to the three", st["total"] == st["done"] == 4, st)
    check("an empty choice is refused", c.post("/api/index", json={"folder_id": fid, "file_ids": []}).status_code == 400)

    print("Stop and use what is done")
    main.gd.fetch_image_bytes = slow
    try:
        c.post("/api/index", json={"folder_id": fid, "all": True, "rebuild": True})
        _time.sleep(0.3)
        c.post("/api/index/stop", json={"folder_id": fid})
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] not in ("indexing", "pending"))
    finally:
        main.gd.fetch_image_bytes = real_fetch
    check("stopped part way through all seven", st["status"] == "stopped" and 4 <= st["done"] < st["total"] == 7, st)
    r = c.post("/api/index/use", json={"folder_id": fid})
    st = c.get("/api/album/%s/status" % fid).json()
    check("the checked photos can be used as they are", r.status_code == 200 and st["status"] == "ready" and st["done"] < 7, st)
    check("and worked on", c.post("/api/cull", json={"folder_id": fid}).status_code == 200)
    c.post("/api/index", json={"folder_id": fid})
    st = ready()
    check("the rest can be scanned later", st["status"] == "ready" and st["done"] == st["total"] == 7, st)

    print("Sorting a partly checked album")
    main.store.conn().execute("UPDATE photos SET ai=NULL WHERE folder_id=? AND file_id='biden.jpg'", (fid,))
    main.store.conn().commit()
    sug = c.post("/api/groups/suggest", json={"folder_id": fid}).json().get("groups") or [{"name": "x", "description": "people"}]
    job = c.post("/api/sort", json={"folder_id": fid, "groups": sug}).json()
    res = wait(lambda: c.get("/api/sort/" + job["job_id"]).json(), lambda j: j["status"] != "running")
    check("a photo Gemini has not checked is listed as not checked, not as Gemini being unsure",
          res["unchecked"] == ["biden.jpg"] and "biden.jpg" not in res["check"], (res["unchecked"], res["check"]))

    print("Links that are not Drive folders")
    for link, words in (("not a drive link", "does not look like"), ("https://photos.app.goo.gl/x", "Google Photos"),
                        ("https://example.com/a", "not a Google Drive link")):
        r = c.post("/api/album", json={"folder": link})
        check("'%s' gets its own advice" % link, r.status_code == 400 and words in r.json()["detail"], r.text)

    print("FaceFinder's own copies are not scanned")

    class Req:
        def __init__(self, out): self.out = out
        def execute(self): return self.out

    class Files:
        tree = {"root": [{"id": "a", "name": "a.jpg", "mimeType": "image/jpeg"},
                         {"id": "copy", "name": "a.jpg", "mimeType": "image/jpeg", "appProperties": {"ff_src": "a"}},
                         {"id": "exp", "name": "FaceFinder - x", "mimeType": main.gd.FOLDER_MIME, "appProperties": {"ff": "1"}},
                         {"id": "sub", "name": "Day 2", "mimeType": main.gd.FOLDER_MIME}],
                "sub": [{"id": "b", "name": "b.jpg", "mimeType": "image/jpeg"}],
                "exp": [{"id": "c", "name": "c.jpg", "mimeType": "image/jpeg", "appProperties": {"ff_src": "b"}}]}
        def list(self, q, **kw): return Req({"files": self.tree[q.split("'")[1]]})

    class Svc:
        def files(self): return Files()
    got = sorted(f["id"] for f in fakedrive_real_list(Svc(), "root"))
    check("exports saved inside the album are left out of the scan", got == ["a", "b"], got)

    print("The shared sample album is protected")
    main.config.SAMPLE_ALBUM = fakedrive.ALBUM_URL
    try:
        r1 = c.post("/api/album/%s/delete" % fid, json={})
        r2 = c.post("/api/index", json={"folder_id": fid, "rebuild": True})
        r3 = c.post("/api/index/stop", json={"folder_id": fid})
        me = c.get("/api/me").json()
    finally:
        main.config.SAMPLE_ALBUM = ""
    check("nobody can delete, rescan or stop the sample album for everyone",
          r1.status_code == r2.status_code == r3.status_code == 403 and "sample album" in r1.json()["detail"], (r1.text, r2.text, r3.text))
    check("the page is told which folder is the sample", me.get("sample_folder_id") == fid, me.get("sample_folder_id"))
    check("the sample album was left as it was", main.store.album(fid)["status"] == "ready")

    print("Delete an album's data")
    before = {k: set(v) for k, v in drive.copies.items()}
    r = c.post("/api/album/%s/delete" % fid, json={})
    check("another session cannot delete it", other.post("/api/album/%s/delete" % fid, json={}).status_code == 403)
    check("deleting removes the scan", r.status_code == 200 and r.json()["deleted"] == 7 and main.store.album(fid) is None, r.text)
    gone = wait(lambda: main.store.cached_ai("obama.jpg:"), lambda v: v is None, 20)   # cleared in the background
    check("...the Gemini notes kept for rescans", gone is None)
    check("...and this account's names", c.post("/api/album", json={"folder": fakedrive.ALBUM_URL}).status_code == 200
          and c.get("/api/album/%s/names" % fid).json()["people"] == [])
    check("nothing in Drive changed", {k: set(v) for k, v in drive.copies.items()} == before)

    print()
    print("%d of %d checks passed" % (sum(checks), len(checks)))
    return all(checks)


if __name__ == "__main__":
    sys.exit(0 if main_test() else 1)
