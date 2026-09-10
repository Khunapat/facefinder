"""Face detection + embedding.

No LLM and no paid API is involved. A face recognition model turns a face into
a vector; two photos of the same person produce two vectors that point in
almost the same direction, so "is this the same person" is a dot product.

Two interchangeable backends:
  insightface (buffalo_l / ArcFace, 512-d)  -- best accuracy, used in Docker
  opencv      (YuNet + SFace, 128-d)        -- pure pip, no build tools, fallback
"""
import os
import threading
import urllib.request

import cv2
import numpy as np

from . import config

_lock = threading.Lock()
_engine = None

MODEL_DIR = os.path.join(config.DATA_DIR, "models")
ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"
YUNET = ("face_detection_yunet_2023mar.onnx", f"{ZOO}/face_detection_yunet")
SFACE = ("face_recognition_sface_2021dec.onnx", f"{ZOO}/face_recognition_sface")


def _download(name: str, base: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, name)
    if not os.path.exists(path):
        urllib.request.urlretrieve(f"{base}/{name}", path)
    return path


class InsightFaceEngine:
    name = "insightface/buffalo_l"
    dim = 512

    def __init__(self):
        from insightface.app import FaceAnalysis

        self.app = FaceAnalysis(
            name=config.MODEL_NAME,
            root=config.DATA_DIR,
            providers=["CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=-1, det_size=(config.DET_SIZE, config.DET_SIZE))

    def detect(self, bgr):
        out = []
        for f in self.app.get(bgr):
            out.append(
                {
                    "embedding": np.asarray(f.normed_embedding, dtype=np.float32),
                    "det_score": float(f.det_score),
                    "bbox": [float(v) for v in f.bbox],
                }
            )
        return out


class OpenCVEngine:
    name = "opencv/yunet+sface"
    dim = 128

    def __init__(self):
        det_path = _download(*YUNET)
        rec_path = _download(*SFACE)
        self.detector = cv2.FaceDetectorYN.create(
            det_path, "", (320, 320), 0.7, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(rec_path, "")

    def detect(self, bgr):
        h, w = bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(bgr)
        if faces is None:
            return []
        out = []
        for row in faces:
            aligned = self.recognizer.alignCrop(bgr, row)
            emb = self.recognizer.feature(aligned).flatten().astype(np.float32)
            emb = emb / (np.linalg.norm(emb) + 1e-9)
            out.append(
                {
                    "embedding": emb,
                    "det_score": float(row[-1]),
                    "bbox": [
                        float(row[0]),
                        float(row[1]),
                        float(row[0] + row[2]),
                        float(row[1] + row[3]),
                    ],
                }
            )
        return out


def engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                try:
                    _engine = InsightFaceEngine()
                except Exception:
                    _engine = OpenCVEngine()
    return _engine


def decode(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    # Very large images cost time without helping detection much.
    h, w = img.shape[:2]
    if max(h, w) > config.THUMB_SIZE:
        s = config.THUMB_SIZE / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img


def embed_image(data: bytes) -> list:
    img = decode(data)
    if img is None:
        return []
    return engine().detect(img)


def best_query_vector(images: list) -> np.ndarray:
    """From the selfies the user uploaded, take the largest face in each and
    average them. Averaging 2-3 shots is noticeably more robust than one."""
    vectors = []
    for data in images:
        faces = embed_image(data)
        if not faces:
            continue
        faces.sort(
            key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]),
            reverse=True,
        )
        vectors.append(faces[0]["embedding"])
    if not vectors:
        return None
    v = np.mean(np.stack(vectors), axis=0)
    return v / (np.linalg.norm(v) + 1e-9)
