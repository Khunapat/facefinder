"""Decisions made from cached data only: no Drive, no Gemini, no waiting.

  dhash()       a 64-bit fingerprint of a photo, taken during the scan, so
                near-identical frames from one burst can be found later
  cull()        keep / reject for the photographer, with a reason per photo
  best_shots()  one person's best photos, for the graduate
"""
import cv2
import numpy as np

from .gemini import FLAWS

# Flaws that make a frame a reject on their own at each strictness.
SERIOUS = {
    "gentle": {"no_subject"},
    "normal": {"blurry", "eyes_closed", "no_subject"},
    "strict": set(FLAWS),
}
MIN_KEEPER = {"gentle": 3, "normal": 5, "strict": 6}   # keeper score below this is a reject
BURST_BITS = 10        # dhash distance at or below which two neighbours are one burst


def dhash(image_bytes: bytes):
    """Difference hash as 16 hex digits, or None for an unreadable image."""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def _distance(a, b) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def bursts(photos: list) -> list:
    """Group neighbouring, near-identical frames. photos must be in shooting
    order (camera file names sort that way). Returns lists of indexes."""
    groups, cur = [], []
    for i, p in enumerate(photos):
        if cur and _distance(photos[cur[-1]].get("dhash"), p.get("dhash")) <= BURST_BITS:
            cur.append(i)
        else:
            if cur:
                groups.append(cur)
            cur = [i]
    if cur:
        groups.append(cur)
    return groups


def _rank(ai) -> tuple:
    """Higher is better. Unchecked photos sort in the middle."""
    if not ai:
        return (5, 0)
    return (ai["keeper"], -len(ai["flaws"]))


def cull(photos: list, strictness: str = "normal") -> dict:
    """photos: [{file_id, name, ai (dict or None), dhash}] for one album.

    Each burst keeps only its best frame; every other photo is kept unless
    Gemini found a serious flaw or scored it low. Photos Gemini has not
    checked are kept, and said so, never rejected unseen."""
    strictness = strictness if strictness in SERIOUS else "normal"
    photos = sorted(photos, key=lambda p: (p.get("name") or "", p["file_id"]))
    keep, reject = [], []
    n_bursts = 0
    for group in bursts(photos):
        best = max(group, key=lambda i: _rank(photos[i].get("ai")))
        if len(group) > 1:
            n_bursts += 1
        for i in group:
            p, ai = photos[i], photos[i].get("ai")
            row = {"file_id": p["file_id"], "name": p.get("name")}
            if i != best:
                row["reason"] = "A similar shot in the same burst is better (%s)" % photos[best].get("name")
                row["similar_to"] = photos[best]["file_id"]
                reject.append(row)
                continue
            if not ai:
                row["reason"] = "Not checked by Gemini yet"
                keep.append(row)
                continue
            row["keeper"] = ai["keeper"]
            bad = [f for f in ai["flaws"] if f in SERIOUS[strictness]]
            if bad or ai["keeper"] < MIN_KEEPER[strictness]:
                row["reason"] = "; ".join(FLAWS[f] for f in bad) or ai["reason"] or "Low score"
                row["flaws"] = ai["flaws"]
                reject.append(row)
            else:
                row["reason"] = ai["reason"]
                keep.append(row)
    keep.sort(key=lambda r: -r.get("keeper", 5))
    return {"keep": keep, "reject": reject, "bursts": n_bursts, "strictness": strictness}


def person_vector(mat: np.ndarray, rows: list, file_ids: list):
    """The face these photos have in common. Each photo may hold several
    faces; the person is the face that best matches a face in every other
    photo. rows[i] is the meta for mat[i]."""
    by_file = {}
    for i, m in enumerate(rows):
        by_file.setdefault(m["file_id"], []).append(i)
    present = [f for f in file_ids if f in by_file]
    if not present:
        return None
    candidates = [i for f in present[:5] for i in by_file[f]]
    others = present[:40]
    best, best_score = None, -1e9
    for c in candidates:
        sims = mat[[i for f in others for i in by_file[f]]] @ mat[c]
        total, k = 0.0, 0
        for f in others:
            n = len(by_file[f])
            total += float(sims[k:k + n].max())
            k += n
        if total > best_score:
            best, best_score = c, total
    return mat[best]


def best_shots(file_ids: list, ai: dict, faces: dict, n: int = 10) -> list:
    """file_ids: one person's photos. ai: {file_id: judgement or None}.
    faces: {file_id: (face side / photo long side, detector score)} for this
    person's face in each photo. Returns the top n with a reason each.

    Order: Gemini's keeper score first (sharp, eyes open, good moment), then
    how big and clear this person is in the frame, so a portrait of them
    beats a crowd shot they happen to be in."""
    scored = []
    for f in dict.fromkeys(file_ids):
        j = ai.get(f)
        side, det = faces.get(f, (0.0, 0.0))
        presence = min(1.0, side / 0.18) * 2 + det       # 0..3
        keeper = j["keeper"] if j else 5
        serious = len([x for x in (j or {}).get("flaws", []) if x in SERIOUS["normal"]])
        scored.append((keeper - 3 * serious + presence, f, j))
    scored.sort(key=lambda s: -s[0])
    out = []
    for score, f, j in scored[:n]:
        out.append({
            "file_id": f,
            "score": round(score, 2),
            "reason": (j or {}).get("reason") or "Clear, large face (Gemini has not checked this photo)",
            "checked": bool(j),
        })
    return out
