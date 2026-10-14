"""Gemini: the curation layer. It never decides who is in a photo; the face
model does that. Gemini answers the questions embeddings cannot:

  judge()          is this photo a keeper? what is happening in it? who is
                   wearing what? Called once per photo during the scan; the
                   result is cached, so everything below reads text, not pixels.
  suggest_groups() look at the album's descriptions and propose ways to sort it
                   ("staff in blue shirts", "students in white uniforms", ...)
  sort_batch()     put each photo into the groups the user described

Two ways to reach Gemini, picked from the environment:
  GEMINI_API_KEY        Gemini Developer API (a Codespace, or local testing)
  GOOGLE_CLOUD_PROJECT  Gemini on Google Cloud (Vertex AI) with the service
                        account's own credentials: no key on Cloud Run.
"""
import json
import os
import threading
import time

import cv2
import numpy as np

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
LOCATION = os.environ.get("GEMINI_LOCATION", "global")
SEND_SIZE = int(os.environ.get("GEMINI_IMAGE_SIZE", "768"))   # long edge sent to Gemini
SORT_BATCH = 40                                                # descriptions per sorting call

FLAWS = {
    "blurry": "Blurry or out of focus",
    "eyes_closed": "Eyes closed",
    "cut_off": "Someone is cut off by the frame",
    "poor_exposure": "Too dark or too bright",
    "blocked": "Something blocks the subject",
    "awkward_moment": "Caught mid-blink, mid-word or mid-movement",
    "no_subject": "No clear subject (accidental shot)",
}

_lock = threading.Lock()
_client = None


def mode():
    """'key', 'cloud' or None (Gemini features switched off)."""
    if os.environ.get("GEMINI", "").lower() in ("0", "off", "false", "no"):
        return None
    if os.environ.get("GEMINI_API_KEY"):
        return "key"
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return "cloud"
    return None


def enabled() -> bool:
    return mode() is not None


def client():
    global _client
    with _lock:
        if _client is None:
            from google import genai

            if mode() == "key":
                _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            else:
                _client = genai.Client(
                    enterprise=True,
                    project=os.environ["GOOGLE_CLOUD_PROJECT"],
                    location=LOCATION,
                )
        return _client


def _call(contents, schema, temperature=0.2):
    """One structured call, retried on rate limits and server errors.
    Returns the parsed JSON object."""
    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
    )
    for attempt in range(5):
        try:
            r = client().models.generate_content(model=MODEL, contents=contents, config=cfg)
            return json.loads(r.text)
        except errors.APIError as e:
            busy = getattr(e, "code", None) in (429, 500, 502, 503, 504)
            if busy and attempt < 4:
                time.sleep(2 * 2 ** attempt)
                continue
            raise


# ------------------------------------------------------------------ judge
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "people": {"type": "array", "items": {"type": "string"}},
        "scene": {"type": "string"},
        "keeper": {"type": "integer", "minimum": 1, "maximum": 10},
        "flaws": {"type": "array", "items": {"type": "string", "enum": list(FLAWS)}},
        "reason": {"type": "string"},
    },
    "required": ["description", "people", "scene", "keeper", "flaws", "reason"],
}

JUDGE_PROMPT = """You are helping an event photographer (graduations, university camps, \
ceremonies) cull and sort their photos. Look at this one photo and answer in English.

description: one or two plain sentences: what is happening and where.
people: one short entry per clearly visible person, left to right, focused on what \
tells people apart in a crowd: clothing and its colours, uniforms, gowns, sashes, \
name tags, lanyards, props they hold. Do not guess names, ages beyond "child/teen/adult", \
or anything about who they are. Empty list if nobody is visible.
scene: a few words for the setting and moment (e.g. "stage, certificate handover", \
"outdoor group photo", "classroom activity", "food table").
keeper: 1-10, how likely a photographer keeps this frame. 9-10 sharp, well framed, \
everyone's eyes open, a good expression or moment. 5-6 usable but ordinary. 1-3 a \
reject. Judge the photo, not the people's looks.
flaws: every flaw that applies, from the allowed list only. Empty if none.
reason: one short line a photographer would agree with, saying why it is or is not a keeper."""


def shrink(image_bytes: bytes) -> bytes:
    """The photo as a JPEG no larger than SEND_SIZE on its long edge."""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("unreadable image")
    h, w = img.shape[:2]
    s = SEND_SIZE / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


def clean_judgement(d: dict) -> dict:
    """Keep only well-formed fields, so the rest of the app can trust them."""
    keeper = d.get("keeper")
    try:
        keeper = min(10, max(1, int(keeper)))
    except (TypeError, ValueError):
        keeper = 5
    return {
        "description": str(d.get("description") or "")[:400],
        "people": [str(p)[:160] for p in (d.get("people") or [])][:20],
        "scene": str(d.get("scene") or "")[:120],
        "keeper": keeper,
        "flaws": [f for f in (d.get("flaws") or []) if f in FLAWS],
        "reason": str(d.get("reason") or "")[:200],
    }


def judge(jpeg: bytes) -> dict:
    """jpeg: the photo, already made small with shrink()."""
    from google.genai import types

    part = types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")
    return clean_judgement(_call([part, JUDGE_PROMPT], JUDGE_SCHEMA))


def as_text(j: dict) -> str:
    """One photo's cached judgement as a line of text for the sorting calls."""
    people = "; ".join(j.get("people") or []) or "nobody visible"
    return "%s | scene: %s | people: %s" % (j.get("description", ""), j.get("scene", ""), people)


# -------------------------------------------------------- sort by groups
SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "description"],
            },
        }
    },
    "required": ["groups"],
}

SUGGEST_PROMPT = """Below are short descriptions of photos from one event album, one per line. \
Propose 2 to 6 useful ways to sort this album into folders, the way the photographer \
would want: first any groups of people who look different from each other (different \
uniforms, shirt colours, gowns or roles, e.g. staff vs. students), then kinds of moments \
(stage, group photos, activities, food). Only propose a group if several photos fit it.

name: a short folder name, 1 to 3 words.
description: one line saying exactly what puts a photo in this group, specific enough \
to apply to a single photo (colours, uniforms, setting).

Descriptions:
"""


def suggest_groups(lines: list) -> list:
    out = _call([SUGGEST_PROMPT + "\n".join(lines)], SUGGEST_SCHEMA, temperature=0.4)
    groups = []
    for g in out.get("groups") or []:
        name = " ".join(str(g.get("name") or "").split())[:60]
        desc = " ".join(str(g.get("description") or "").split())[:240]
        if name and desc:
            groups.append({"name": name, "description": desc})
    return groups[:6]


SORT_SCHEMA = {
    "type": "object",
    "properties": {
        "photos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "groups": {"type": "array", "items": {"type": "integer"}},
                    "sure": {"type": "boolean"},
                },
                "required": ["n", "groups", "sure"],
            },
        }
    },
    "required": ["photos"],
}

SORT_PROMPT = """Sort event photos into folders. The folders, numbered, with what puts a \
photo in each (the user may have written them in Thai or English):
%s

Below, one photo per line, numbered, as a description of what is in it. For every photo \
give the numbers of ALL folders it belongs in (a photo with both staff and students goes \
in both), or an empty list if it fits none. Set sure to false when the description does \
not say enough to decide, rather than guessing.

Photos:
%s"""


def sort_batch(lines: list, groups: list) -> list:
    """lines: photo descriptions; groups: [{name, description}].
    Returns one {"groups": [index, ...], "sure": bool} per line, in order."""
    folders = "\n".join(
        "%d. %s: %s" % (i + 1, g["name"], g["description"]) for i, g in enumerate(groups)
    )
    photos = "\n".join("%d. %s" % (i + 1, t) for i, t in enumerate(lines))
    out = _call([SORT_PROMPT % (folders, photos)], SORT_SCHEMA, temperature=0.0)
    got = {}
    for p in out.get("photos") or []:
        try:
            n = int(p.get("n")) - 1
        except (TypeError, ValueError):
            continue
        idx = sorted({int(g) - 1 for g in (p.get("groups") or [])
                      if isinstance(g, int) and 1 <= g <= len(groups)})
        got[n] = {"groups": idx, "sure": bool(p.get("sure"))}
    # A line Gemini skipped is not a "fits nothing"; it goes to the check pile.
    return [got.get(i, {"groups": [], "sure": False}) for i in range(len(lines))]
