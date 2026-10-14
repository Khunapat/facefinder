"""Runtime configuration, all from environment variables (cloud-friendly)."""
import os

# --- Google OAuth (create these in Google Cloud Console -> Credentials) ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Public base URL of the deployed app, e.g. https://facefinder.example.com
# Must match the Authorized redirect URI registered in Google Cloud Console.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
REDIRECT_URI = PUBLIC_BASE_URL + "/oauth2/callback"

# drive.readonly  -> read the photographer's shared album
# drive.file      -> create/write only files this app makes (the destination copies)
#
# With those two the app can only write into folders it created itself, so a
# destination folder the user pastes cannot be written to directly; the export
# then falls back to a new folder in My Drive. Set DRIVE_ACCESS=full to request
# the whole-Drive scope instead and write straight into any folder the user can
# edit. Both drive.readonly and drive are "restricted" scopes to Google, so this
# does not change the verification tier, only what the consent screen says.
DRIVE_ACCESS = os.environ.get("DRIVE_ACCESS", "limited").strip().lower()
if DRIVE_ACCESS == "full":
    SCOPES = ["https://www.googleapis.com/auth/drive"]
else:
    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ]
SCOPES += ["openid", "https://www.googleapis.com/auth/userinfo.email"]

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me")

# --- Storage ---
# On hosts with a persistent volume set DATA_DIR to it; otherwise the index is
# rebuilt after a restart (indexing is the only expensive step).
DATA_DIR = os.environ.get("DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "index.sqlite")

# Where the face model files live. Deliberately separate from DATA_DIR:
# the Docker image bakes the model in at build time, and DATA_DIR is the
# path you mount a persistent volume on. If they were the same directory
# the volume would shadow the baked-in model and the container would
# re-download ~300 MB on first boot.
MODEL_ROOT = os.environ.get("MODEL_ROOT", DATA_DIR)

# --- Face engine ---
# Cosine similarity threshold. ArcFace/buffalo_l: >0.5 is a confident match,
# 0.35-0.5 is "probably them". We default low and let the user tighten it.
DEFAULT_THRESHOLD = float(os.environ.get("DEFAULT_THRESHOLD", "0.38"))
DET_SIZE = int(os.environ.get("DET_SIZE", "640"))
MODEL_NAME = os.environ.get("MODEL_NAME", "buffalo_l")
# Pixel width of the Drive thumbnail we run detection on. Bigger = better on
# faces far from the camera, but slower.
THUMB_SIZE = int(os.environ.get("THUMB_SIZE", "1600"))
INDEX_WORKERS = int(os.environ.get("INDEX_WORKERS", "4"))
# Similarity at which two faces are linked when grouping the whole album into
# people. Stricter than DEFAULT_THRESHOLD: a wrong link merges two people.
CLUSTER_THRESHOLD = float(os.environ.get("CLUSTER_THRESHOLD", "0.46"))
COPY_WORKERS = int(os.environ.get("COPY_WORKERS", "4"))
# Parallel Gemini calls while scanning. They wait on the network, not the CPU.
GEMINI_WORKERS = int(os.environ.get("GEMINI_WORKERS", "12"))

def _ensure_dir(path: str, var: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise SystemExit(
            "Cannot create %s=%s (%s).\n"
            "Point it somewhere writable, or unset it to fall back to DATA_DIR."
            % (var, path, e.strerror)
        ) from e


_ensure_dir(DATA_DIR, "DATA_DIR")
_ensure_dir(MODEL_ROOT, "MODEL_ROOT")
