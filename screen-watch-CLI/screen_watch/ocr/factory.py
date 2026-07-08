"""OCR 引擎工厂：PaddleOCR 优先，不可用时回退 macOS Vision"""

from __future__ import annotations

import sys
from typing import Any, Literal

from screen_watch.utils.logger import setup_logger

logger = setup_logger()

OcrBackend = Literal["auto", "paddle", "vision"]


def _paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


def require_ocr_deps() -> None:
    """确保至少一种 OCR 后端可用"""
    if _paddle_available():
        return
    if sys.platform == "darwin":
        from screen_watch.ocr.vision_engine import require_vision_deps

        require_vision_deps()
        return
    raise RuntimeError(
        "无可用 OCR 引擎。请安装: pip install -e '.[capture]' (macOS Vision) "
        "或 pip install -e '.[ocr,capture]' (PaddleOCR，需 Python 3.9–3.13)"
    )


def get_ocr_engine(backend: OcrBackend = "auto", **kwargs: Any):
    if backend == "paddle":
        from screen_watch.ocr.paddle_engine import PaddleOcrEngine

        return PaddleOcrEngine.get_instance(**kwargs)

    if backend == "vision":
        if sys.platform != "darwin":
            raise RuntimeError("Vision OCR 仅支持 macOS")
        from screen_watch.ocr.vision_engine import VisionOcrEngine

        return VisionOcrEngine.get_instance(**kwargs)

    # auto
    if _paddle_available():
        logger.info("OCR 引擎: PaddleOCR")
        from screen_watch.ocr.paddle_engine import PaddleOcrEngine

        return PaddleOcrEngine.get_instance(**kwargs)

    if sys.platform == "darwin":
        logger.info("OCR 引擎: macOS Vision（PaddleOCR 不可用时的回退）")
        from screen_watch.ocr.vision_engine import VisionOcrEngine

        return VisionOcrEngine.get_instance(**kwargs)

    raise RuntimeError(
        "无可用 OCR 引擎。macOS 请 pip install -e '.[capture]'；"
        "其他平台请 pip install -e '.[ocr,capture]'（Python ≤3.13）"
    )
