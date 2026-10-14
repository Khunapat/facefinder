"""A stand-in for Gemini, so the curation features can be tested and clicked
through without a Google Cloud project or an API key.

It looks at real pixels, crudely: sharpness from the Laplacian, exposure from
brightness, and the colour of the middle-lower part of the frame as "what people
are wearing". Sorting matches colour words. Good enough to exercise every route
and screen; it says nothing about how well the real Gemini judges photos.
"""
import re

import cv2
import numpy as np

COLOURS = {
    "red": (0, 0, 200), "orange": (0, 140, 255), "yellow": (0, 220, 230),
    "green": (40, 160, 40), "blue": (200, 90, 20), "purple": (140, 40, 120),
    "pink": (180, 140, 240), "white": (235, 235, 235), "grey": (128, 128, 128),
    "black": (25, 25, 25),
}


def _colour(bgr) -> str:
    return min(COLOURS, key=lambda c: float(np.sum((np.array(COLOURS[c]) - bgr) ** 2)))


def judge(jpeg: bytes) -> dict:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = cv2.Laplacian(grey, cv2.CV_64F).var()
    light = float(grey.mean())
    h, w = grey.shape
    shirt = img[int(h * 0.65):int(h * 0.95), int(w * 0.3):int(w * 0.7)].reshape(-1, 3).mean(axis=0)
    colour = _colour(shirt)

    flaws = []
    if sharp < 60:
        flaws.append("blurry")
    if light < 45 or light > 225:
        flaws.append("poor_exposure")
    keeper = 8 - 3 * len(flaws)
    return {
        "description": "People at an event, the nearest wearing %s." % colour,
        "people": ["adult in a %s top" % colour],
        "scene": "event photo",
        "keeper": max(1, keeper),
        "flaws": flaws,
        "reason": "Sharp and well exposed" if not flaws else "Soft focus or poor light",
    }


def suggest_groups(lines: list) -> list:
    counts = {}
    for line in lines:
        for c in COLOURS:
            if re.search(r"\b%s\b" % c, line):
                counts[c] = counts.get(c, 0) + 1
    top = sorted(counts, key=lambda c: -counts[c])[:3]
    return [{"name": "%s tops" % c.title(), "description": "people wearing %s" % c} for c in top]


def sort_batch(lines: list, groups: list) -> list:
    out = []
    for line in lines:
        hit = [i for i, g in enumerate(groups)
               if any(re.search(r"\b%s\b" % c, g["description"].lower()) and re.search(r"\b%s\b" % c, line)
                      for c in COLOURS)]
        out.append({"groups": hit, "sure": True})
    return out


def install():
    """Swap the app's Gemini calls for this stand-in and switch the features on."""
    from app import gemini

    gemini.mode = lambda: "fake"
    gemini.enabled = lambda: True
    gemini.judge = lambda jpeg: gemini.clean_judgement(judge(jpeg))
    gemini.suggest_groups = suggest_groups
    gemini.sort_batch = sort_batch
