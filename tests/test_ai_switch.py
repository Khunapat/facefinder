"""The "check with AI" switch, and Meta's Muse Spark as the AI.

Covers:
  - a scan with the switch off finds faces and sends no photo to the AI;
    adding the notes later checks only the photos, without finding faces again
  - Meta's Model API transport: the request it sends (model, key, the photo,
    strict JSON schema), the retries and fallbacks, and its errors
  - the pages naming the model in use, and the privacy wording for Meta

What it cannot cover: the real Meta Model API. That needs a key and is
checked by hand with a real call.

Run:  python -m tests.test_ai_switch
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DATA_DIR", os.path.join(ROOT, "data"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "dev")
os.environ["GEMINI"] = "off"

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, gemini, main  # noqa: E402
from tests import fakedrive, fakegemini  # noqa: E402

TMP = tempfile.mkdtemp(prefix="facefinder-aiswitch-")
config.DB_PATH = os.path.join(TMP, "index.sqlite")
ALBUM = os.path.join(TMP, "album")
shutil.copytree(os.path.join(ROOT, "tests", "img"), ALBUM)
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


class Reply:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body


GOOD = {"description": "Two people in blue shirts hold a banner.", "people": ["blue shirt", "blue shirt"],
        "scene": "outdoor event", "keeper": 7, "flaws": [], "unsure": False, "reason": "Clear moment, both faces sharp"}


def answer(obj, fence=False):
    text = json.dumps(obj)
    if fence:
        text = "```json\n" + text + "\n```"
    return Reply(200, {"model": "muse-spark-1.1", "choices": [{"message": {"content": text}}]})


def meta_tests():
    print("Meta's Model API")
    real_post, real_sleep = httpx.post, gemini.time.sleep
    gemini.time.sleep = lambda s: None
    os.environ.pop("GEMINI", None)
    os.environ.pop("META_API_KEY", None)
    os.environ.pop("MODEL_API_KEY", None)
    os.environ["AI_PROVIDER"] = "meta"
    try:
        check("Meta without a key leaves the AI off", gemini.mode() is None and not gemini.enabled())
        os.environ["META_API_KEY"] = "test-key"
        check("with a key, Meta is the AI", gemini.mode() == "meta" and gemini.name() == "Muse Spark")

        sent = []

        def post(url, json=None, headers=None, timeout=None):
            sent.append({"url": url, "body": copy.deepcopy(json), "headers": headers})
            return replies.pop(0)
        httpx.post = post

        jpeg = open(os.path.join(ALBUM, "obama.jpg"), "rb").read()
        replies = [answer(GOOD)]
        out = gemini.judge(gemini.shrink(jpeg))
        req = sent[0]
        content = req["body"]["messages"][0]["content"]
        check("it calls chat completions on api.meta.ai", req["url"] == "https://api.meta.ai/v1/chat/completions", req["url"])
        check("with the key as a bearer token", req["headers"]["Authorization"] == "Bearer test-key")
        check("asks Muse Spark", req["body"]["model"] == "muse-spark-1.1", req["body"]["model"])
        check("sends the photo as a JPEG image part, then the instructions",
              content[0]["type"] == "image_url" and content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
              and content[1]["type"] == "text" and "event photographer" in content[1]["text"], [c["type"] for c in content])
        fmt = req["body"]["response_format"]
        check("asks for strict JSON in the judging schema",
              fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
              and fmt["json_schema"]["schema"]["additionalProperties"] is False
              and "keeper" in fmt["json_schema"]["schema"]["required"], fmt)
        check("the answer is checked like Gemini's and names the model",
              out["keeper"] == 7 and out["model"] == "muse-spark-1.1" and out["flaws"] == [], out)

        sent.clear()
        replies = [Reply(400, {"error": "reasoning_effort is not supported"}), answer(GOOD)]
        gemini.judge(gemini.shrink(jpeg))
        check("a model without the reasoning setting is asked again without it",
              "reasoning_effort" in sent[0]["body"] and "reasoning_effort" not in sent[1]["body"], len(sent))

        sent.clear()
        replies = [Reply(400, {"error": "unsupported json schema keyword: minimum"}), answer(GOOD, fence=True)]
        out = gemini.judge(gemini.shrink(jpeg))
        check("a schema it cannot take falls back to plain JSON, schema in the prompt",
              sent[1]["body"]["response_format"] == {"type": "json_object"}
              and "JSON schema" in sent[1]["body"]["messages"][0]["content"][-1]["text"] and out["keeper"] == 7, sent[1]["body"].get("response_format"))
        check("a JSON answer wrapped in a code fence is still read", out["reason"].startswith("Clear moment"))

        sent.clear()
        replies = [Reply(429, "busy"), Reply(503, "busy"), answer(GOOD)]
        gemini.judge(gemini.shrink(jpeg))
        check("busy answers are retried", len(sent) == 3, len(sent))

        replies = [Reply(401, {"error": "bad key"})]
        try:
            gemini.judge(gemini.shrink(jpeg))
            check("a refused key raises an error", False)
        except gemini.MetaError as e:
            check("a refused key raises an error", e.code == 401, e)

        replies = [answer({"photos": [{"n": 1, "groups": [1], "sure": True}, {"n": 2, "groups": [], "sure": True}]})]
        got = gemini.sort_batch(["two people in blue shirts", "a cake"], [{"name": "Blue", "description": "blue shirts"}])
        check("sorting works through Meta too", got == [{"groups": [0], "sure": True}, {"groups": [], "sure": True}], got)

        print("Pages with Meta's model")
        c = TestClient(main.app)
        page = c.get("/").text
        check("the start page names Muse Spark", "Muse Spark judges photo quality" in page)
        check("...and no longer says Gemini, except the sample album's made-up people",
              page.count("Gemini") == page.count("created with Gemini") == 1, page.count("Gemini"))
        check("...nor Vertex AI", "Vertex" not in page)
        priv = c.get("/privacy").text
        check("the privacy policy says photos go to Meta's Model API",
              "Meta Model API" in priv and "Vertex" not in priv and "Google's models" not in priv)
        check("/api/me tells the page the model's name", c.get("/api/me").json()["ai_name"] == "Muse Spark")
    finally:
        httpx.post, gemini.time.sleep = real_post, real_sleep
        os.environ.pop("AI_PROVIDER", None)
        os.environ.pop("META_API_KEY", None)
    page = TestClient(main.app).get("/").text
    check("without Meta, the page is the Gemini one as before",
          page == open(os.path.join(ROOT, "app", "static", "index.html"), encoding="utf-8").read())


def switch_tests():
    print("The AI switch")
    fakedrive.install(os.path.join(TMP, "drive"), image_dirs=[ALBUM])
    fakegemini.install()
    calls = []
    real_judge = gemini.judge

    def counted(jpeg):
        calls.append(1)
        return real_judge(jpeg)
    gemini.judge = counted
    c = TestClient(main.app)
    c.get("/dev/login", follow_redirects=False)
    fid = fakedrive.ALBUM_ID
    c.post("/api/album", json={"folder": fakedrive.ALBUM_URL})

    seen = []
    real_status = main.store.judged_count

    c.post("/api/index", json={"folder_id": fid, "ai": False})
    st = wait(lambda: seen.append(c.get("/api/album/%s/status" % fid).json()) or seen[-1],
              lambda s: s["status"] in ("ready", "error"))
    check("with the switch off, every photo gets its faces", st["status"] == "ready" and st["done"] == 5, st)
    check("...and no photo is sent to the AI", not calls and st["judged"] == 0, (len(calls), st["judged"]))
    running = [s for s in seen if s["status"] in ("pending", "indexing")]
    check("while it runs, the page is told no AI check is coming",
          all(s["gemini"] is False for s in running if s["status"] == "indexing"), [s["gemini"] for s in running])
    check("once ready, the album can still have AI notes added", st["gemini"] is True)
    people = c.post("/api/people", json={"folder_id": fid}).json()
    check("Everyone works without AI notes", "groups" in people or "people" in people, list(people)[:3])

    found = []
    real_analyze = main.faces.analyze

    def analyze(data):
        found.append(1)
        return real_analyze(data)
    main.faces.analyze = analyze
    try:
        c.post("/api/index", json={"folder_id": fid, "ai": True})
        st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    finally:
        main.faces.analyze = real_analyze
    check("adding the notes later checks every photo with the AI", st["judged"] == st["done"] == 5 and len(calls) == 5,
          (st["judged"], len(calls)))
    check("...without finding the faces again", not found, len(found))

    calls.clear()
    c.post("/api/index", json={"folder_id": fid, "rebuild": True})
    st = wait(lambda: c.get("/api/album/%s/status" % fid).json(), lambda s: s["status"] in ("ready", "error"))
    check("a scan that does not mention the switch uses the AI, as before (kept notes, no new calls)",
          st["judged"] == 5 and not calls, (st["judged"], len(calls)))
    gemini.judge = real_judge
    main.store.judged_count = real_status


if __name__ == "__main__":
    meta_tests()
    switch_tests()
    print()
    print("%d of %d checks passed" % (sum(checks), len(checks)))
    sys.exit(0 if all(checks) else 1)
