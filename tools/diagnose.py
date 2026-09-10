"""Work out why an index run is slow: CPU, or fetching the photos?

Run it in a second terminal while a scan is going. It does not touch the
running server or the index beyond reading it.

    python -m tools.diagnose
"""
import os
import sqlite3
import time

from app import config


def _fmt(sec):
    return "%.0f ms" % (sec * 1000) if sec < 1 else "%.1f s" % sec


def main():
    print("=" * 62)
    print("FaceFinder scan diagnosis")
    print("=" * 62)

    # ---- what the index says --------------------------------------------
    photos = faces = 0
    if os.path.exists(config.DB_PATH):
        c = sqlite3.connect(config.DB_PATH)
        try:
            photos = c.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            faces = c.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
            for row in c.execute(
                "SELECT name, status, total, done, faces FROM albums"
            ):
                print("\nalbum   : %s" % row[0])
                print("status  : %s" % row[1])
                print("progress: %s of %s photos, %s faces" % (row[3], row[2], row[4]))
        finally:
            c.close()
    else:
        print("\nno index yet at %s" % config.DB_PATH)

    per_photo = (faces / photos) if photos else 0.0
    if photos:
        print("density : %.1f faces per photo" % per_photo)

    # ---- how fast is THIS machine at the actual work? --------------------
    print("\nmeasuring this machine (no network involved)...")
    from app import faces as ff

    eng = ff.engine()
    print("engine  : %s" % eng.name)

    sample = os.path.join("tests", "img", "two_people.jpg")
    data = open(sample, "rb").read()
    ff.embed_image(data)  # warm up
    runs = 3
    t = time.perf_counter()
    for _ in range(runs):
        found = ff.embed_image(data)
    cpu = (time.perf_counter() - t) / runs
    n = max(len(found), 1)

    # ~90 ms detect + ~273 ms per face measured on a 4-core reference box
    fixed = cpu * 0.15
    each = (cpu - fixed) / n
    predicted = fixed + each * (per_photo or n)

    print("\nCPU only, %d-face sample : %s" % (n, _fmt(cpu)))
    print("  implied cost per face  : %s" % _fmt(each))
    if per_photo:
        print("  so YOUR photos (%.1f faces) should cost ~%s each"
              % (per_photo, _fmt(predicted)))

    print("\n" + "-" * 62)
    print("Compare that with your real rate.")
    print("Take two progress readings a few minutes apart:")
    print("    seconds elapsed / photos gained = your real seconds per photo")
    print()
    if per_photo:
        print("  CPU-only predicts : %s per photo" % _fmt(predicted))
        print("  if your real rate is within ~2x of that -> CPU bound, this is")
        print("     simply how fast this machine does the maths")
        print("  if it is much slower -> the time is going into FETCHING photos,")
        print("     not the maths. Check the server log for lines reading")
        print("     'full-size download for ...'")
    print("-" * 62)


if __name__ == "__main__":
    main()
