"""OCR 模块"""

from screen_watch.ocr.factory import OcrBackend, get_ocr_engine, require_ocr_deps
from screen_watch.ocr.paddle_engine import PaddleOcrEngine

__all__ = ["OcrBackend", "PaddleOcrEngine", "get_ocr_engine", "require_ocr_deps"]
