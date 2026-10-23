"""Face ID: two small ONNX models, no photo is ever kept.

  SCRFD-500M       finds faces and five points on each (eyes, nose, mouth corners)
  MobileFaceNet    turns an aligned face into 512 numbers (a "faceprint")

Both come from the InsightFace "buffalo_sc" pack and are downloaded on first use
(15 MB). Note: those pretrained models are free for non-commercial research and
personal use only. Needs: numpy, onnxruntime, opencv-python-headless
(install the "identity" extra).
"""
from __future__ import annotations

import io
import os
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

MODEL_URL = os.getenv(
    "IRAS_FACE_MODEL_URL",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip",
)
DET_FILE = "det_500m.onnx"
REC_FILE = "w600k_mbf.onnx"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
_ARCFACE_POINTS = [
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
]


class FaceUnavailable(RuntimeError):
    """Face ID cannot run here (tools or models missing). The message says why."""


class FaceError(ValueError):
    """The picture cannot be used (no face, several faces, too small). Safe to show the user."""


@dataclass
class Face:
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    score: float
    points: list  # five (x, y): left eye, right eye, nose, left mouth, right mouth

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def turn(self) -> float:
        """How far the head is turned: nose offset from the middle of the eyes, in eye distances."""
        (lx, _), (rx, _), (nx, _) = self.points[0], self.points[1], self.points[2]
        eyes = max(1e-6, abs(rx - lx))
        return float((nx - (lx + rx) / 2.0) / eyes)


class FaceEngine:
    def __init__(self, model_dir: str | os.PathLike | None = None) -> None:
        base = model_dir or os.getenv("IRAS_FACE_MODEL_DIR") or Path(tempfile.gettempdir()) / "iras-face-models"
        self.dir = Path(base)
        self._lock = threading.Lock()
        self._det = None
        self._rec = None

    # ---------- setup ----------
    @staticmethod
    def tools_missing() -> str:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            return f"Face ID needs numpy, onnxruntime and opencv-python-headless on the server ({exc.name} is missing)."
        return ""

    def models_ready(self) -> bool:
        return (self.dir / DET_FILE).exists() and (self.dir / REC_FILE).exists()

    def _download(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=90) as response:
                data = response.read()
            with zipfile.ZipFile(io.BytesIO(data)) as pack:
                for name in (DET_FILE, REC_FILE):
                    member = next((m for m in pack.namelist() if m.endswith(name)), None)
                    if member is None:
                        raise FaceUnavailable(f"The model pack has no {name}.")
                    target = self.dir / name
                    temp = target.with_suffix(".part")
                    temp.write_bytes(pack.read(member))
                    temp.replace(target)
        except FaceUnavailable:
            raise
        except Exception as exc:  # network, zip, disk
            raise FaceUnavailable(f"Could not download the face models ({type(exc).__name__}: {exc}).") from exc

    def _load(self) -> None:
        missing = self.tools_missing()
        if missing:
            raise FaceUnavailable(missing)
        import onnxruntime as ort

        with self._lock:
            if self._det is not None:
                return
            if not self.models_ready():
                self._download()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            providers = ["CPUExecutionProvider"]
            det = ort.InferenceSession(str(self.dir / DET_FILE), options, providers=providers)
            if len(det.get_outputs()) != 9:
                raise FaceUnavailable("The face detector model is not the expected one.")
            self._rec = ort.InferenceSession(str(self.dir / REC_FILE), options, providers=providers)
            self._det = det

    # ---------- pictures ----------
    @staticmethod
    def decode(data: bytes):
        import cv2
        import numpy as np

        if not data or len(data) > MAX_IMAGE_BYTES:
            raise FaceError("The picture is empty or too large.")
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceError("I could not read that picture.")
        height, width = image.shape[:2]
        biggest = max(height, width)
        if biggest > 1600:
            scale = 1600.0 / biggest
            image = cv2.resize(image, (int(width * scale), int(height * scale)))
        return image

    # ---------- finding faces ----------
    def detect(self, image, threshold: float = 0.5) -> list[Face]:
        import cv2
        import numpy as np

        self._load()
        size = 640
        height, width = image.shape[:2]
        scale = min(size / height, size / width)
        new_w, new_h = max(1, int(width * scale)), max(1, int(height * scale))
        canvas = np.zeros((size, size, 3), np.uint8)
        canvas[:new_h, :new_w] = cv2.resize(image, (new_w, new_h))
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outs = self._det.run(None, {self._det.get_inputs()[0].name: blob})

        boxes, scores, points = [], [], []
        for index, stride in enumerate((8, 16, 32)):
            raw_scores = outs[index].reshape(-1)
            raw_boxes = outs[index + 3].reshape(-1, 4) * stride
            raw_points = outs[index + 6].reshape(-1, 10) * stride
            cells = size // stride
            grid = np.stack(np.mgrid[:cells, :cells][::-1], axis=-1).astype(np.float32).reshape(-1, 2) * stride
            centers = np.repeat(grid, 2, axis=0)  # two anchors per cell
            keep = raw_scores >= threshold
            if not keep.any():
                continue
            c, b, k = centers[keep], raw_boxes[keep], raw_points[keep]
            boxes.append(np.stack([c[:, 0] - b[:, 0], c[:, 1] - b[:, 1], c[:, 0] + b[:, 2], c[:, 1] + b[:, 3]], axis=1))
            points.append(np.stack([c[:, [0]] + k[:, 0::2], c[:, [1]] + k[:, 1::2]], axis=-1))
            scores.append(raw_scores[keep])
        if not boxes:
            return []
        boxes = np.concatenate(boxes) / scale
        points = np.concatenate(points) / scale
        scores = np.concatenate(scores)
        rects = [[float(x1), float(y1), float(x2 - x1), float(y2 - y1)] for x1, y1, x2, y2 in boxes]
        kept = cv2.dnn.NMSBoxes(rects, [float(s) for s in scores], threshold, 0.4)
        faces = []
        for i in np.array(kept).reshape(-1):
            x1, y1, x2, y2 = boxes[i]
            faces.append(Face((float(x1), float(y1), float(x2), float(y2)), float(scores[i]), points[i].tolist()))
        faces.sort(key=lambda f: f.width, reverse=True)
        return faces

    # ---------- the faceprint ----------
    def embed(self, image, face: Face):
        import cv2
        import numpy as np

        self._load()
        source = np.array(face.points, np.float32)
        target = np.array(_ARCFACE_POINTS, np.float32)
        matrix, _ = cv2.estimateAffinePartial2D(source, target, method=cv2.LMEDS)
        if matrix is None:
            raise FaceError("I could not line up that face. Look straight at the camera.")
        crop = cv2.warpAffine(image, matrix, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(crop, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        vector = self._rec.run(None, {self._rec.get_inputs()[0].name: blob})[0][0].astype(np.float32)
        return vector / (float(np.linalg.norm(vector)) + 1e-9)

    def analyze(self, data: bytes):
        """Every face in a picture, plus the faceprint of the biggest one. Returns (faces, vector or None)."""
        image = self.decode(data)
        faces = self.detect(image)
        return faces, (self.embed(image, faces[0]) if faces else None)

    def one_face(self, data: bytes, min_width: float = 60.0):
        """Decode a picture that must hold exactly one usable face. Returns (face, faceprint)."""
        image = self.decode(data)
        faces = self.detect(image)
        if not faces:
            raise FaceError("I cannot see a face. Face the camera in good light.")
        if len(faces) > 1 and faces[1].width > 0.6 * faces[0].width:
            raise FaceError("I see more than one face. Only one person in the picture, please.")
        face = faces[0]
        if face.width < min_width:
            raise FaceError("Your face is too small in the picture. Move closer.")
        return face, self.embed(image, face)


_ENGINE: FaceEngine | None = None


def engine() -> FaceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = FaceEngine()
    return _ENGINE
