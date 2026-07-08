"""OCR 前图像预处理"""

from __future__ import annotations

from typing import Any

import numpy as np


def apply_preprocess(image: np.ndarray, steps: list[str]) -> np.ndarray:
    if image is None or image.size == 0:
        return image

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("请安装 OCR 依赖: pip install -e '.[ocr]'") from exc

    img = image.copy()
    for step in steps:
        if step == "grayscale":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif step == "scale_2x":
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        elif step == "invert_if_dark":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if float(gray.mean()) < 128.0:
                img = cv2.bitwise_not(img)
        else:
            raise ValueError(f"未知预处理步骤: {step}")
    return img


def save_debug_image(image: np.ndarray, path: str) -> None:
    import cv2
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), image)
