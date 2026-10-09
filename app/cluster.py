"""Group every face in an album into people, with no names known up front.

The album scan already stored one vector per face. Two faces of the same person
have a high cosine similarity, so "who is in this album" is a graph problem:
link every pair of faces above a threshold, then let the labels settle
(Chinese Whispers, the same approach dlib uses for face clustering).
"""
import numpy as np


def _neighbours(mat: np.ndarray, thr: float, chunk: int = 1024):
    """For each face, the indices and similarities of the faces linked to it."""
    n = len(mat)
    idx, wts = [], []
    for start in range(0, n, chunk):
        sims = mat[start:start + chunk] @ mat.T
        for r in range(sims.shape[0]):
            row = sims[r]
            row[start + r] = 0.0            # no self-link
            hit = np.nonzero(row >= thr)[0]
            idx.append(hit.astype(np.int32))
            wts.append(row[hit].astype(np.float32))
    return idx, wts


def chinese_whispers(mat: np.ndarray, thr: float, iters: int = 30, seed: int = 7):
    """Return one integer label per row of mat."""
    n = len(mat)
    labels = np.arange(n)
    if n < 2:
        return labels
    idx, wts = _neighbours(mat, thr)
    rng = np.random.default_rng(seed)       # fixed seed: same album, same groups
    for _ in range(iters):
        changed = 0
        for i in rng.permutation(n):
            if idx[i].size == 0:
                continue
            uniq, inv = np.unique(labels[idx[i]], return_inverse=True)
            best = uniq[np.argmax(np.bincount(inv, weights=wts[i]))]
            if best != labels[i]:
                labels[i] = best
                changed += 1
        if not changed:
            break
    return labels


def _centroids(mat: np.ndarray, labels: np.ndarray):
    uniq = np.unique(labels)
    cents = np.stack([mat[labels == u].mean(axis=0) for u in uniq])
    cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
    return uniq, cents


def _merge_close(mat: np.ndarray, labels: np.ndarray, thr: float):
    """One person can split in two (cap on / cap off). Averaged vectors are much
    less noisy than single faces, so groups whose averages agree are joined."""
    uniq, cents = _centroids(mat, labels)
    if len(uniq) < 2:
        return labels
    parent = list(range(len(uniq)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    sims = cents @ cents.T
    for a, b in zip(*np.nonzero(np.triu(sims, 1) >= thr)):
        parent[find(int(a))] = find(int(b))
    remap = {u: uniq[find(k)] for k, u in enumerate(uniq)}
    return np.array([remap[v] for v in labels])


def _side(bbox) -> float:
    if not bbox or len(bbox) < 4:
        return 1e9                      # unknown size: do not penalise
    return min(bbox[2] - bbox[0], bbox[3] - bbox[1])


def group_album(mat, meta, thr: float, min_det: float = 0.6, min_side: float = 30.0):
    """Return a list of people, biggest first.

    Each person: {id, cover:{file_id, face_idx}, count, photos:[{file_id, name,
    score, confident}]}. A group photo appears under every person in it.
    """
    n = len(meta)
    if n == 0:
        return []

    # Groups are formed from clear faces only; tiny background faces give noisy
    # vectors that glue strangers together. They are attached afterwards.
    good = np.array(
        [m["det_score"] >= min_det and _side(m["bbox"]) >= min_side for m in meta]
    )
    if not good.any():
        good[:] = True
    gi = np.nonzero(good)[0]

    labels = chinese_whispers(mat[gi], thr)
    labels = _merge_close(mat[gi], labels, thr + 0.06)
    uniq, cents = _centroids(mat[gi], labels)

    face_label = np.full(n, -1)
    face_label[gi] = np.searchsorted(uniq, labels)

    rest = np.nonzero(~good)[0]
    if len(rest):
        sims = mat[rest] @ cents.T
        best = sims.argmax(axis=1)
        ok = sims[np.arange(len(rest)), best] >= thr
        face_label[rest[ok]] = best[ok]

    people = []
    for k in range(len(uniq)):
        members = np.nonzero(face_label == k)[0]
        sims = mat[members] @ cents[k]

        photos = {}                     # one row per photo: its best face
        cover, cover_score = None, -1.0
        for i, s in zip(members, sims):
            m = meta[i]
            if s > photos.get(m["file_id"], (-1.0, None))[0]:
                photos[m["file_id"]] = (float(s), m["name"])
            if good[i]:                 # the cover should be a clear, typical face
                q = float(s) * m["det_score"] * min(1.0, _side(m["bbox"]) / 120.0)
                if q > cover_score:
                    cover, cover_score = m, q
        if cover is None:
            continue

        rows = [
            {
                "file_id": fid,
                "name": name,
                "score": round(s, 4),
                "confident": s >= 0.5,
            }
            for fid, (s, name) in photos.items()
        ]
        rows.sort(key=lambda r: -r["score"])
        people.append(
            {
                "id": "%s:%d" % (cover["file_id"], cover["face_idx"]),
                "cover": {"file_id": cover["file_id"], "face_idx": cover["face_idx"]},
                "count": len(rows),
                "photos": rows,
            }
        )
    people.sort(key=lambda p: -p["count"])
    return people
