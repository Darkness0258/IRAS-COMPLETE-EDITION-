from __future__ import annotations

"""IRAS-managed local bridge for OmniParser.

This process runs inside the user's OmniParser virtual environment. It exposes
three loopback endpoints:

* ``/probe/``: readiness/capabilities plus lightweight text-model warmup state.
* ``/parse_text/``: EasyOCR-only text grounding for controller-owned ROIs.
* ``/parse/``: full OmniParser semantics, loaded lazily on first full request.

The bridge imports torch before EasyOCR/OmniParser on Windows to avoid the
PaddleOCR/PyTorch DLL load-order conflict observed with OmniParser's normal
import path. R5 also warms EasyOCR in a background thread after the HTTP server
starts so cold model initialization can overlap with application focus/launch.
"""

import argparse
import base64
import io
import os
from pathlib import Path
import sys
import threading
import time
import hmac
import types

import torch  # preload first: important on Windows
from fastapi import FastAPI, Header, HTTPException
from PIL import Image
from pydantic import BaseModel
import uvicorn


class ParseRequest(BaseModel):
    base64_image: str


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IRAS OmniParser bridge")
    parser.add_argument("--omniparser-root", required=True)
    parser.add_argument("--som-model-path", default="")
    parser.add_argument("--caption-model-name", default="florence2")
    parser.add_argument("--caption-model-path", default="../../weights/icon_caption_florence")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--box-threshold", type=float, default=0.05)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument(
        "--control-token",
        default=os.getenv("IRAS_OMNIPARSER_CONTROL_TOKEN", ""),
    )
    parser.add_argument(
        "--prewarm-text",
        action="store_true",
        help="Warm the EasyOCR text model in a background thread after startup.",
    )
    return parser.parse_args()


ARGS = _arguments()
ROOT = Path(ARGS.omniparser_root).expanduser().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI()
_easyocr_reader = None
_easyocr_lock = threading.Lock()
_easyocr_state_lock = threading.Lock()
_easyocr_state = "cold"
_easyocr_error = ""
_easyocr_warmup_ms: int | None = None
_easyocr_warmup_started_at: float | None = None
_easyocr_thread: threading.Thread | None = None
_full_parser = None
_full_parser_lock = threading.Lock()
_full_state_lock = threading.Lock()
_full_model_state = "cold"
_full_model_error = ""
_full_model_warmup_ms: int | None = None
_full_model_device = ""


def _decode_image(value: str) -> Image.Image:
    try:
        raw = base64.b64decode(value, validate=True)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.load()
        return image
    except Exception as exc:  # noqa: BLE001 - HTTP boundary
        raise HTTPException(status_code=400, detail=f"invalid image payload: {exc}") from exc


def _set_easyocr_state(
    state: str,
    *,
    error: str = "",
    warmup_ms: int | None = None,
    started_at: float | None = None,
) -> None:
    global _easyocr_state, _easyocr_error, _easyocr_warmup_ms, _easyocr_warmup_started_at
    with _easyocr_state_lock:
        _easyocr_state = state
        _easyocr_error = error
        if warmup_ms is not None:
            _easyocr_warmup_ms = int(warmup_ms)
        if started_at is not None:
            _easyocr_warmup_started_at = float(started_at)


def _easyocr_status() -> dict:
    with _easyocr_state_lock:
        return {
            "text_model_state": _easyocr_state,
            "text_model_loaded": _easyocr_reader is not None,
            "text_model_error": _easyocr_error or None,
            "text_model_warmup_ms": _easyocr_warmup_ms,
            "text_model_warmup_started_at": _easyocr_warmup_started_at,
        }


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader

    # Holding this lock across initialization is intentional. If the first OCR
    # request arrives while the background warmup is still loading EasyOCR, that
    # request waits for the same initialization instead of starting a duplicate
    # model load or broadening immediately to the expensive full parser.
    with _easyocr_lock:
        if _easyocr_reader is not None:
            return _easyocr_reader
        started = time.perf_counter()
        started_at = time.time()
        _set_easyocr_state("warming", error="", started_at=started_at)
        try:
            import easyocr

            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception as exc:  # noqa: BLE001 - model boundary
            elapsed = int((time.perf_counter() - started) * 1000)
            _set_easyocr_state(
                "failed",
                error=f"{type(exc).__name__}: {exc}",
                warmup_ms=elapsed,
            )
            raise
        _easyocr_reader = reader
        elapsed = int((time.perf_counter() - started) * 1000)
        _set_easyocr_state("ready", error="", warmup_ms=elapsed)
        return _easyocr_reader


def _warm_easyocr_background() -> None:
    try:
        _get_easyocr_reader()
    except Exception:
        # The status endpoint records the failure. /parse_text/ may surface the
        # same failure, but full OmniParser remains available as a last resort.
        return


def _start_easyocr_prewarm() -> bool:
    global _easyocr_thread
    if not ARGS.prewarm_text:
        return False
    if _easyocr_reader is not None:
        return False
    if _easyocr_thread is not None and _easyocr_thread.is_alive():
        return False
    thread = threading.Thread(
        target=_warm_easyocr_background,
        name="iras-easyocr-prewarm",
        daemon=True,
    )
    _easyocr_thread = thread
    thread.start()
    return True


def _set_full_model_state(
    state: str,
    *,
    error: str = "",
    warmup_ms: int | None = None,
    device: str | None = None,
) -> None:
    global _full_model_state, _full_model_error, _full_model_warmup_ms, _full_model_device
    with _full_state_lock:
        _full_model_state = str(state)
        _full_model_error = str(error or "")
        if warmup_ms is not None:
            _full_model_warmup_ms = int(warmup_ms)
        if device is not None:
            _full_model_device = str(device)


def _full_model_status() -> dict:
    with _full_state_lock:
        return {
            "full_model_state": _full_model_state,
            "full_model_loaded": _full_parser is not None,
            "full_model_error": _full_model_error or None,
            "full_model_warmup_ms": _full_model_warmup_ms,
            "full_model_device": _full_model_device or None,
        }


def _configured_full_device() -> str:
    requested = str(ARGS.device or "cpu").strip().lower() or "cpu"
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda"):
        if not torch.cuda.is_available():
            return "cpu"
        # Maxwell-era adapters may still make torch.cuda.is_available() true
        # even when the installed PyTorch/CUDA build no longer ships kernels
        # for that compute capability. Fail over to CPU before model loading
        # instead of surfacing a late no-kernel-image 500 from /parse/.
        try:
            major, _minor = torch.cuda.get_device_capability(0)
            if int(major) < 6:
                return "cpu"
        except Exception:
            return "cpu"
    return requested


def _install_paddle_stub() -> None:
    if not _truthy(os.getenv("IRAS_OMNIPARSER_DISABLE_PADDLE"), default=True):
        return
    paddle = types.ModuleType("paddleocr")

    class PaddleOCR:
        def __init__(self, *args, **kwargs):
            pass

        def ocr(self, *args, **kwargs):
            raise RuntimeError(
                "PaddleOCR is disabled in the IRAS OmniParser bridge; "
                "EasyOCR is the configured OCR backend."
            )

    paddle.PaddleOCR = PaddleOCR
    sys.modules["paddleocr"] = paddle


def _load_omniparser_utils():
    # Upstream util.utils creates an EasyOCR Reader at module import. Reuse the
    # reader IRAS already warmed instead of allocating a second OCR model.
    _install_paddle_stub()
    import easyocr

    original_reader = easyocr.Reader
    easyocr.Reader = lambda *args, **kwargs: _get_easyocr_reader()
    try:
        from util import utils as omni_utils
    finally:
        easyocr.Reader = original_reader
    # If util.utils was imported before the shim, still force the shared reader.
    try:
        omni_utils.reader = _get_easyocr_reader()
    except Exception:
        pass
    return omni_utils


class _IRASFullOmniParser:
    """Small upstream-compatible parser that honors IRAS's device setting."""

    def __init__(self, config: dict):
        self.config = dict(config)
        self.device = _configured_full_device()
        utils = _load_omniparser_utils()
        self._utils = utils
        self.som_model = utils.get_yolo_model(
            model_path=self.config.get("som_model_path") or None,
            device=self.device,
        )
        self.caption_model_processor = utils.get_caption_model_processor(
            model_name=self.config["caption_model_name"],
            model_name_or_path=self.config["caption_model_path"],
            device=self.device,
        )

    def parse(self, image_base64: str):
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image.load()
        box_overlay_ratio = max(image.size) / 3200
        draw_bbox_config = {
            "text_scale": 0.8 * box_overlay_ratio,
            "text_thickness": max(int(2 * box_overlay_ratio), 1),
            "text_padding": max(int(3 * box_overlay_ratio), 1),
            "thickness": max(int(3 * box_overlay_ratio), 1),
        }
        (text, ocr_bbox), _ = self._utils.check_ocr_box(
            image,
            display_img=False,
            output_bb_format="xyxy",
            easyocr_args={"text_threshold": 0.8},
            use_paddleocr=False,
        )
        # Upstream master currently turns an empty OCR list into None and then
        # immediately calls zip(ocr_bbox, ...), which raises TypeError on
        # icon-only or low-text screenshots. Give it a 1-pixel sentinel box so
        # full visual semantics still run, then remove the sentinel from output.
        sentinel = "__IRAS_OCR_SENTINEL__"
        used_sentinel = not bool(ocr_bbox)
        if used_sentinel:
            ocr_bbox = [[0, 0, 1, 1]]
            text = [sentinel]
        labeled, _coords, parsed = self._utils.get_som_labeled_img(
            image,
            self.som_model,
            BOX_TRESHOLD=float(self.config["BOX_TRESHOLD"]),
            output_coord_in_ratio=True,
            ocr_bbox=ocr_bbox,
            draw_bbox_config=draw_bbox_config,
            caption_model_processor=self.caption_model_processor,
            ocr_text=text,
            use_local_semantics=True,
            iou_threshold=0.7,
            scale_img=False,
            batch_size=32 if self.device == "cpu" else 128,
        )
        if used_sentinel:
            parsed = [
                item for item in parsed
                if str((item or {}).get("content") or "") != sentinel
            ]
        return labeled, parsed


def _get_full_parser():
    global _full_parser
    if _full_parser is not None:
        return _full_parser
    with _full_parser_lock:
        if _full_parser is not None:
            return _full_parser
        started = time.perf_counter()
        device = _configured_full_device()
        _set_full_model_state("warming", error="", device=device)
        try:
            parser = _IRASFullOmniParser(
                {
                    "som_model_path": ARGS.som_model_path or None,
                    "caption_model_name": ARGS.caption_model_name,
                    "caption_model_path": ARGS.caption_model_path,
                    "device": device,
                    "BOX_TRESHOLD": float(ARGS.box_threshold),
                }
            )
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            _set_full_model_state(
                "failed",
                error=f"{type(exc).__name__}: {exc}",
                warmup_ms=elapsed,
                device=device,
            )
            raise
        _full_parser = parser
        elapsed = int((time.perf_counter() - started) * 1000)
        _set_full_model_state("ready", error="", warmup_ms=elapsed, device=parser.device)
        return _full_parser


def _require_control_token(value: str | None) -> None:
    expected = str(ARGS.control_token or "")
    provided = str(value or "")
    if not expected or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="invalid IRAS control token")


@app.on_event("startup")
def _startup() -> None:
    _start_easyocr_prewarm()


@app.get("/probe/")
def probe() -> dict:
    return {
        "message": "IRAS OmniParser bridge ready",
        "bridge": "iras-v3.7-r5",
        "capabilities": ["text_roi", "full_parse", "text_background_prewarm"],
        "text_prewarm_enabled": bool(ARGS.prewarm_text),
        **_easyocr_status(),
        **_full_model_status(),
    }


@app.post("/control/stop")
def control_stop(
    x_iras_control_token: str | None = Header(
        default=None,
        alias="X-IRAS-Control-Token",
    ),
) -> dict:
    _require_control_token(x_iras_control_token)

    def _exit() -> None:
        # Bound to loopback by the IRAS runtime and authenticated with a random
        # per-process token. Exit after the response can be flushed.
        time.sleep(0.15)
        os._exit(0)

    threading.Thread(target=_exit, name="iras-omniparser-stop", daemon=True).start()
    return {"ok": True, "status": "stopping"}


@app.post("/parse_text/")
def parse_text(request: ParseRequest) -> dict:
    started = time.perf_counter()
    image = _decode_image(request.base64_image)
    width, height = image.size
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="empty image")

    import numpy as np

    try:
        reader = _get_easyocr_reader()
        result = reader.readtext(
            np.asarray(image),
            detail=1,
            paragraph=False,
            text_threshold=0.68,
            low_text=0.35,
            link_threshold=0.35,
        )
    except Exception as exc:  # noqa: BLE001 - HTTP/model boundary
        raise HTTPException(
            status_code=503,
            detail=f"text model unavailable: {type(exc).__name__}: {exc}",
        ) from exc

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
        **_easyocr_status(),
    }


@app.post("/parse/")
def parse_full(request: ParseRequest) -> dict:
    started = time.perf_counter()
    try:
        parser = _get_full_parser()
        labeled, parsed = parser.parse(request.base64_image)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - model/HTTP boundary
        elapsed = int((time.perf_counter() - started) * 1000)
        current = _full_model_status()
        _set_full_model_state(
            "failed",
            error=f"{type(exc).__name__}: {exc}",
            warmup_ms=elapsed,
            device=str(current.get("full_model_device") or _configured_full_device()),
        )
        raise HTTPException(
            status_code=503,
            detail=f"full model unavailable: {type(exc).__name__}: {exc}",
        ) from exc
    return {
        "som_image_base64": labeled,
        "parsed_content_list": parsed,
        "latency": time.perf_counter() - started,
        "mode": "full",
        **_full_model_status(),
    }


if __name__ == "__main__":
    # Environment opt-out remains available even when a caller uses an older
    # launch command without the new flag.
    if not ARGS.prewarm_text and _truthy(
        os.getenv("IRAS_OMNIPARSER_TEXT_PREWARM"), default=False
    ):
        ARGS.prewarm_text = True
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, reload=False, workers=1)
