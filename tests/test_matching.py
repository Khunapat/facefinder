"""Sanity check on the face engine: does the same person score high and a
different person score low, on real photos?

Run:  python -m tests.test_matching
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import faces  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")


def read(name):
    with open(os.path.join(IMG, name), "rb") as fh:
        return fh.read()


def main():
    eng = faces.engine()
    print("engine:", eng.name, "dim:", eng.dim)
    print()

    query = faces.best_query_vector([read("obama.jpg")])
    assert query is not None, "no face found in the query image"

    rows = []
    for path in sorted(glob.glob(os.path.join(IMG, "*.jpg"))):
        name = os.path.basename(path)
        found = faces.embed_image(read(name))
        best = max((float(f["embedding"] @ query) for f in found), default=-1.0)
        rows.append((name, len(found), best))

    print(f"{'photo':<18}{'faces':>6}{'best score':>12}   verdict")
    for name, n, score in rows:
        verdict = "MATCH" if score >= 0.38 else "no match"
        print(f"{name:<18}{n:>6}{score:>12.3f}   {verdict}")
    print()

    got = dict((n, s) for n, _, s in rows)
    checks = [
        ("same person, different photo", got["obama2.jpg"] >= 0.38),
        ("same person, low resolution", got["obama_small.jpg"] >= 0.38),
        ("different person rejected", got["biden.jpg"] < 0.38),
        ("found in a group photo", got["two_people.jpg"] >= 0.38),
        ("group photo has 2 faces", dict((n, c) for n, c, _ in rows)["two_people.jpg"] == 2),
    ]
    ok = True
    for label, passed in checks:
        print(("  PASS  " if passed else "  FAIL  ") + label)
        ok = ok and passed
    print()
    margin = min(got["obama2.jpg"], got["obama_small.jpg"]) - got["biden.jpg"]
    print(f"separation between same-person and different-person: {margin:.3f}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
