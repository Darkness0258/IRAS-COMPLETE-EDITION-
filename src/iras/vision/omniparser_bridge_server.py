from __future__ import annotations

"""IRAS-managed local bridge for OmniParser.

This process runs inside the user's OmniParser virtual environment.  It exposes
three loopback endpoints:

* ``/probe/``: readiness/capabilities.
* ``/parse_text/``: lightweight EasyOCR-only text grounding for narrow ROIs.
* ``/parse/``: full OmniParser semantics, loaded lazily on first full request.

The bridge deliberately imports torch before EasyOCR/OmniParser on Windows to
avoid the PaddleOCR/PyTorch DLL load-order conflict observed with OmniParser's
normal import path.
"""

import argparse
import base64
import io
from pathlib import Path
import sys
import threading
import time

import torch  # preload first: important on Windows
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
import uvicorn


class ParseRequest(BaseModel):
    base64_image: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IRAS OmniParser bridge")
    parser.add_argument("--omniparser-root", required=True)
    parser.add_argument("--caption-model-name", default="florence2")
    parser.add_argument("--caption-model-path", default="../../weights/icon_caption_florence")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--box-threshold", type=float, default=0.05)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    return parser.parse_args()


ARGS = _arguments()
ROOT = Path(ARGS.omniparser_root).expanduser().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI()
_easyocr_reader = None
_easyocr_lock = threading.Lock()
_full_parser = None
_full_parser_lock = threading.Lock()


def _decode_image(value: str) -> Image.Image:
    try:
        raw = base64.b64decode(value, validate=True)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.load()
        return image
    except Exception as exc:  # noqa: BLE001 - HTTP boundary
        raise HTTPException(status_code=400, detail=f"invalid image payload: {exc}") from exc


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader
    with _easyocr_lock:
        if _easyocr_reader is None:
            import easyocr

            # The fast text path is intentionally CPU-local and narrowly scoped.
            _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _easyocr_reader


def _get_full_parser():
    global _full_parser
    if _full_parser is not None:
        return _full_parser
    with _full_parser_lock:
        if _full_parser is None:
            from util.omniparser import Omniparser

            _full_parser = Omniparser(
                {
                    "som_model_path": None,
                    "caption_model_name": ARGS.caption_model_name,
                    "caption_model_path": ARGS.caption_model_path,
                    "device": ARGS.device,
                    "BOX_TRESHOLD": float(ARGS.box_threshold),
                }
            )
    return _full_parser


@app.get("/probe/")
def probe() -> dict:
    return {
        "message": "IRAS OmniParser bridge ready",
        "bridge": "iras-v3.7-r4",
        "capabilities": ["text_roi", "full_parse"],
        "full_model_loaded": _full_parser is not None,
        "text_model_loaded": _easyocr_reader is not None,
    }


@app.post("/parse_text/")
def parse_text(request: ParseRequest) -> dict:
    started = time.perf_counter()
    image = _decode_image(request.base64_image)
    width, height = image.size
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="empty image")

    import numpy as np

    result = _get_easyocr_reader().readtext(
        np.asarray(image),
        detail=1,
        paragraph=False,
        text_threshold=0.68,
        low_text=0.35,
        link_threshold=0.35,
    )

    elements: list[dict] = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box, text, confidence = item[0], str(item[1] or "").strip(), item[2]
        if not text or not isinstance(box, (list, tuple)) or len(box) < 4:
            continue
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            x1, x2 = max(0.0, min(xs)), min(float(width), max(xs))
            y1, y2 = max(0.0, min(ys)), min(float(height), max(ys))
            conf = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError, IndexError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        elements.append(
            {
                "type": "text",
                "bbox": [x1 / width, y1 / height, x2 / width, y2 / height],
                # This endpoint is controller-internal. Making the OCR span
                # actionable lets the bounded fast path click/type at the text
                # center while normal public computer-use still uses full scene
                # grounding and all existing confidence/freshness guards.
                "interactivity": True,
                "content": text,
                "confidence": conf,
                "source": "easyocr_text_roi",
            }
        )

    return {
        "parsed_content_list": elements,
        "latency": time.perf_counter() - started,
        "mode": "text_roi",
        "image_size": [width, height],
    }


@app.post("/parse/")
def parse_full(request: ParseRequest) -> dict:
    started = time.perf_counter()
    parser = _get_full_parser()
    labeled, parsed = parser.parse(request.base64_image)
    return {
        "som_image_base64": labeled,
        "parsed_content_list": parsed,
        "latency": time.perf_counter() - started,
        "mode": "full",
    }


if __name__ == "__main__":
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, reload=False, workers=1)
