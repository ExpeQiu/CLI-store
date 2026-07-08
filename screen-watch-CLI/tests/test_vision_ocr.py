"""Vision OCR 测试（macOS）"""

from __future__ import annotations

import sys

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Vision OCR 仅 macOS")


@pytest.fixture
def sample_viewer_image() -> np.ndarray:
    import cv2

    img = np.zeros((120, 400, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)
    cv2.putText(
        img,
        "687 watched",
        (10, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    # 中文在默认字体可能渲染差，额外放 ASCII 数字供测试
    cv2.putText(img, "687", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    return img


def test_vision_ocr_recognizes_digits(sample_viewer_image: np.ndarray) -> None:
    pytest.importorskip("Vision")
    from screen_watch.ocr.vision_engine import VisionOcrEngine

    engine = VisionOcrEngine(min_confidence=0.3)
    lines = engine.recognize(sample_viewer_image)
    text = " ".join(item["text"] for item in lines)
    assert "687" in text.replace(" ", "")
