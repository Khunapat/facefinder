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
    """Visual-similarity groups, not proof of a temporal burst."""
    groups, cur = [], []
    for i, photo in enumerate(photos):
        # Anchor to the first image to avoid chaining dissimilar endpoints.
        if cur and _distance(photos[cur[0]].get("dhash"), photo.get("dhash")) <= BURST_BITS:
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


def _alone(ai, strictness: str):
    """The pile and reason for one checked photo, judged on its own."""
    bad = [f for f in ai["flaws"] if f in SERIOUS[strictness]]
    if ai["keeper"] < REJECT_BELOW[strictness] and (bad or ai["keeper"] <= 2):
        return "reject", "; ".join(FLAWS[f] for f in bad) or ai.get("reason") or "Low quality score"
    if bad or ai["keeper"] < REVIEW_BELOW[strictness]:
        return "review", ai.get("reason") or "Needs a look"
    return "keep", ai.get("reason") or "Usable for the album"


def cull(photos: list, strictness: str = "normal") -> dict:
    """photos: [{file_id, name, ai (dict or None), dhash}] for one album.

    Suggestions in three piles, each photo with a reason. Nothing unseen or
    uncertain is rejected: a photo Gemini did not check, or was unsure about,
    goes to review. Of near-identical frames, a copy is rejected only when a
    clearly better copy is in keep; other look-alikes go to review."""
    strictness = strictness if strictness in SERIOUS else "normal"
    photos = sorted(photos, key=lambda p: (p.get("name") or "", p["file_id"]))
    out = {"keep": [], "review": [], "reject": []}
    n_groups = 0
    for group in bursts(photos):
        n_groups += int(len(group) > 1)
        checked = [i for i in group if photos[i].get("ai") and not photos[i]["ai"].get("unsure")]
        best = max(checked, key=lambda i: _rank(photos[i]["ai"])) if checked else None
        best_pile = _alone(photos[best]["ai"], strictness)[0] if best is not None else None
        for i in group:
            p, ai = photos[i], photos[i].get("ai")
            row = {"file_id": p["file_id"], "name": p.get("name")}
            if not ai:
                row["reason"] = "Gemini could not check this photo"
                out["review"].append(row)
                continue
            row.update(keeper=ai["keeper"], flaws=ai["flaws"])
            if ai.get("unsure"):
                row["reason"] = "Gemini was not sure: " + (ai.get("reason") or "details are unclear")
                out["review"].append(row)
                continue
            pile, row["reason"] = _alone(ai, strictness)
            if best is not None and i != best and pile != "reject":
                b = photos[best]
                row["similar_to"], row["similar_name"] = b["file_id"], b.get("name")
                same = _distance(p.get("dhash"), b.get("dhash")) <= SAME_BITS
                if same and best_pile == "keep" and ai["keeper"] <= b["ai"]["keeper"] - 2:
                    pile, row["reason"] = "reject", "A clearly better copy is kept (%s)" % b.get("name")
                else:
                    pile, row["reason"] = "review", "Looks like %s; keep both if the moment differs" % b.get("name")
            out[pile].append(row)
    for pile in out.values():
        pile.sort(key=lambda row: -row.get("keeper", 5))
    out.update(bursts=n_groups, strictness=strictness)
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
        if not j or j.get("unsure") or j["keeper"] < 4:
            continue
        keeper = j["keeper"]
        serious = len([x for x in j.get("flaws", []) if x in SERIOUS["normal"]])
        base_score = keeper - 3 * serious + presence
        if base_score < 4:
            continue
        pool.append({"f": f, "j": j, "base": base_score,
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
        c["score"] = score(c)
        picks.append(c)
        pool.remove(c)
    return [{
        "file_id": c["f"],
        "score": round(c["score"], 2),
        "reason": (c["j"] or {}).get("reason") or "Quality reason unavailable; review this photo",
        "description": (c["j"] or {}).get("description") or "",
        "checked": bool(c["j"]),
    } for c in picks]
