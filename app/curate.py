"""Decisions made from cached data only: no Drive, no Gemini, no waiting.

  dhash()       a 64-bit fingerprint of a photo, taken during the scan, so
                near-identical frames from one burst can be found later
  cull()        keep / reject for the photographer, with a reason per photo
  best_shots()  one person's best photos, for the graduate
"""
import cv2
import numpy as np

from .gemini import FLAWS

# Strictness changes where the lines are drawn, never what Gemini observed.
# A frame with one of these flaws is a reject only if it also scores low;
# with a good score it goes to Review, because a flawed frame can still be the
# only record of a moment.
SERIOUS = {
    "gentle": {"no_subject"},
    "normal": {"blurry", "eyes_closed", "no_subject"},
    "strict": set(FLAWS),
}
REJECT_BELOW = {"gentle": 3, "normal": 4, "strict": 5}   # keeper score under this: reject
REVIEW_BELOW = {"gentle": 4, "normal": 6, "strict": 7}   # under this (or flawed): review
BURST_BITS = 10        # dhash distance at or below which two neighbours are one burst
SAME_BITS = 4          # this close is the same frame twice: the weaker one is a reject


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

    Three piles, each photo with a reason:
      keep    good frames, and the best frame of each burst
      review  borderline frames, flawed frames that are the only shot of their
              moment, near-duplicates that differ a little, anything Gemini was
              unsure about or could not check
      reject  clear mistakes, and copies of a better frame in the same burst
    Nothing is rejected unseen: a photo Gemini has not checked goes to review."""
    strictness = strictness if strictness in SERIOUS else "normal"
    photos = sorted(photos, key=lambda p: (p.get("name") or "", p["file_id"]))
    out = {"keep": [], "review": [], "reject": []}
    n_bursts = 0
    for group in bursts(photos):
        best = max(group, key=lambda i: _rank(photos[i].get("ai")))
        if len(group) > 1:
            n_bursts += 1
        for i in group:
            p, ai = photos[i], photos[i].get("ai")
            row = {"file_id": p["file_id"], "name": p.get("name")}
            if ai:
                row["keeper"], row["flaws"] = ai["keeper"], ai["flaws"]
            if i != best:
                b = photos[best]
                row["similar_to"] = b["file_id"]
                same = _distance(p.get("dhash"), b.get("dhash")) <= SAME_BITS
                close = _rank(ai)[0] >= _rank(b.get("ai"))[0] - 1
                if same or not close:
                    row["reason"] = "A better frame of the same shot is kept (%s)" % b.get("name")
                    out["reject"].append(row)
                else:
                    row["reason"] = "Similar to %s; keep it too if the moment differs" % b.get("name")
                    out["review"].append(row)
                continue
            if not ai:
                row["reason"] = "Gemini could not check this photo"
                out["review"].append(row)
                continue
            bad = [f for f in ai["flaws"] if f in SERIOUS[strictness]]
            k = ai["keeper"]
            if k < REJECT_BELOW[strictness] and (bad or k <= 2):
                row["reason"] = "; ".join(FLAWS[f] for f in bad) or ai["reason"] or "Low score"
                out["reject"].append(row)
            elif bad or k < REVIEW_BELOW[strictness] or ai.get("unsure"):
                row["reason"] = ("; ".join(FLAWS[f] for f in bad) + " - but it may be the only shot"
                                 if bad else ai["reason"] or "Borderline")
                out["review"].append(row)
            else:
                row["reason"] = ai["reason"]
                out["keep"].append(row)
    for pile in out.values():
        pile.sort(key=lambda r: -r.get("keeper", 5))
    out.update(bursts=n_bursts, strictness=strictness)
    return out


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


def best_shots(file_ids: list, ai: dict, faces: dict, n: int = 10, prints: dict = None) -> list:
    """file_ids: one person's photos. ai: {file_id: judgement or None}.
    faces: {file_id: (face side / photo long side, detector score)} for this
    person's face in each photo. prints: {file_id: dhash}. Returns the top n
    with a reason each.

    Order: Gemini's keeper score first (sharp, a clear moment), then how big
    and clear this person is in the frame, so a portrait of them beats a crowd
    shot they happen to be in. Then variety: each pick pushes down photos that
    look like it or come from the same scene, so ten near-identical frames of
    one pose never fill the list. Fewer than n good photos gives fewer picks."""
    prints = prints or {}
    pool = []
    for f in dict.fromkeys(file_ids):
        j = ai.get(f)
        side, det = faces.get(f, (0.0, 0.0))
        presence = min(1.0, side / 0.18) * 2 + det       # 0..3
        keeper = j["keeper"] if j else 5
        serious = len([x for x in (j or {}).get("flaws", []) if x in SERIOUS["normal"]])
        pool.append({"f": f, "j": j, "base": keeper - 3 * serious + presence,
                     "scene": ((j or {}).get("scene") or "").strip().lower()})
    picks = []
    while pool and len(picks) < n:
        def score(c):
            s = c["base"]
            for p in picks:
                if _distance(prints.get(c["f"]), prints.get(p["f"])) <= 2 * BURST_BITS:
                    s -= 3                                # looks like a photo already picked
                elif c["scene"] and c["scene"] == p["scene"]:
                    s -= 0.75                             # same kind of moment
            return s
        c = max(pool, key=score)
        if picks and c["base"] < 4:                       # do not pad the list with weak photos
            break
        c["score"] = score(c)
        picks.append(c)
        pool.remove(c)
    return [{
        "file_id": c["f"],
        "score": round(c["score"], 2),
        "reason": (c["j"] or {}).get("reason") or "Clear, large face (Gemini has not checked this photo)",
        "checked": bool(c["j"]),
    } for c in picks]
