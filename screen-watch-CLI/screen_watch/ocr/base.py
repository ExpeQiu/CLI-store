"""OCR 引擎协议"""

from __future__ import annotations

from typing import Any, Protocol


class OcrEngine(Protocol):
    name: str

    def recognize(self, image: Any) -> list[dict]:
        """输入 numpy BGR，返回 [{text, confidence, bbox}, ...]"""
