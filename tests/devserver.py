"""Run the real app against a local stand-in for Google Drive.

    python -m tests.devserver            then open http://127.0.0.1:8077/dev/login

The album is the sample photos under tests/img (and tests/img_extra if you have
it). Paste any Drive-looking link, for example the one printed at start-up.
"Copied" folders are written under data/dev-export so you can look at them.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PORT = int(os.environ.get("PORT", "8077"))
os.environ.setdefault("DATA_DIR", os.path.join(ROOT, "data"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "dev")
os.environ.setdefault("PUBLIC_BASE_URL", "http://127.0.0.1:%d" % PORT)

from app import config, gemini, main  # noqa: E402
from tests import fakedrive, fakegemini  # noqa: E402

config.DB_PATH = os.path.join(config.DATA_DIR, "dev-index.sqlite")
fakedrive.install(os.path.join(config.DATA_DIR, "dev-export"))
# Real Gemini when a key or project is set, the stand-in otherwise.
if not gemini.enabled():
    fakegemini.install()

if __name__ == "__main__":
    import uvicorn

    print("Sign in:      http://127.0.0.1:%d/dev/login" % PORT)
    print("Album link:   " + fakedrive.ALBUM_URL)
    print("Locked dest:  " + fakedrive.LOCKED_URL)
    uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="warning")
