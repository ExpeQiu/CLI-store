"""PaddleOCR 引擎封装"""

from __future__ import annotations

from typing import Any

from screen_watch.utils.logger import setup_logger

logger = setup_logger()


def require_ocr_deps() -> None:
    try:
        import paddleocr  # noqa: F401
        import cv2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "缺少 OCR 依赖，请执行: pip install -e '.[ocr]'"
        ) from exc


class PaddleOcrEngine:
    _instance: "PaddleOcrEngine | None" = None

    def __init__(
        self,
        *,
        lang: str = "ch",
        use_gpu: bool = False,
        min_confidence: float = 0.6,
    ) -> None:
        self.lang = lang
        self.use_gpu = use_gpu
        self.min_confidence = min_confidence
        self._ocr = None

    @classmethod
    def get_instance(cls, **kwargs: Any) -> "PaddleOcrEngine":
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        require_ocr_deps()
        from paddleocr import PaddleOCR

        logger.info("加载 PaddleOCR 模型 lang=%s", self.lang)
        self._ocr = PaddleOCR(
            use_angle_cls=True,
            lang=self.lang,
            use_gpu=self.use_gpu,
            show_log=False,
        )

    def recognize(self, image: Any) -> list[dict]:
        """
        输入: numpy BGR
        输出: [{text, confidence, bbox}, ...]
        """
        if image is None or getattr(image, "size", 0) == 0:
            return []

        self._ensure_loaded()
        result = self._ocr.ocr(image, cls=True)
        lines: list[dict] = []
        if not result or not result[0]:
            return lines

        for item in result[0]:
            bbox, (text, conf) = item
            if not text or conf < self.min_confidence:
                continue
            lines.append(
                {
                    "text": str(text).strip(),
                    "confidence": float(conf),
                    "bbox": bbox,
                }
            )
        return lines
