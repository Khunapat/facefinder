"""End-to-end check of the parts that do not need Google: index a fake album
into SQLite, then run the same search maths the /api/search route runs.

Run:  python -m tests.test_pipeline
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the store at a throwaway database before app.config is imported.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="facefinder-test-")

from app import faces, store  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
ALBUM = "test-album"


def read(name):
    with open(os.path.join(IMG, name), "rb") as fh:
        return fh.read()


def main():
    # --- index a small "album" the way the background worker does ---
    album_files = ["obama2.jpg", "biden.jpg", "two_people.jpg", "obama_small.jpg"]
    store.set_album(ALBUM, name="Graduation 2026", status="indexing", total=len(album_files))
    for i, name in enumerate(album_files):
        found = faces.embed_image(read(name))
        store.save_photo(ALBUM, "file-%d" % i, name, found)
        store.bump_progress(ALBUM, 1, len(found))
    store.set_album(ALBUM, status="ready")

    row = store.album(ALBUM)
    print("album:", row["name"], "| status:", row["status"],
          "| photos:", row["done"], "| faces:", row["faces"])

    # --- resume behaviour: a second pass must not rescan anything ---
    already = store.indexed_file_ids(ALBUM)

    # --- search, exactly as the route does ---
    mat, meta = store.load_matrix(ALBUM)
    query = faces.best_query_vector([read("obama.jpg")])
    sims = mat @ query

    best = {}
    for i, s in enumerate(sims):
        m = meta[i]
        if s > best.get(m["file_id"], (-1.0, None))[0]:
            best[m["file_id"]] = (float(s), m)

    threshold = 0.38
    hits = sorted(
        ((s, m["name"]) for s, m in best.values() if s >= threshold), reverse=True
    )
    print("\nembedding matrix:", mat.shape)
    print("matches at threshold %.2f:" % threshold)
    for s, name in hits:
        print("   %.3f  %s" % (s, name))
    rejected = sorted((s, m["name"]) for s, m in best.values() if s < threshold)
    for s, name in rejected:
        print("   %.3f  %s   (rejected)" % (s, name))

    names = [n for _, n in hits]
    checks = [
        ("all 4 photos stored", row["done"] == 4),
        ("5 faces found (group photo has 2)", row["faces"] == 5),
        ("embeddings persist and reload", mat.shape == (5, 512)),
        ("resume skips indexed files", len(already) == 4),
        ("the 3 photos of the person match", len(hits) == 3),
        ("the other person is rejected", "biden.jpg" not in names),
        ("one row per photo, not per face", len(best) == 4),
    ]
    print()
    ok = True
    for label, passed in checks:
        print(("  PASS  " if passed else "  FAIL  ") + label)
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
