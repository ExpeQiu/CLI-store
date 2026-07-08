"""macOS Vision 框架 OCR（无需 Paddle，Python 3.14 可用）"""

from __future__ import annotations

from typing import Any

from screen_watch.utils.logger import setup_logger

logger = setup_logger()


def require_vision_deps() -> None:
    try:
        import Vision  # noqa: F401
        import cv2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Vision OCR 依赖，请执行: pip install -e '.[capture]'"
        ) from exc


class VisionOcrEngine:
    name = "vision"

    def __init__(self, *, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    @classmethod
    def get_instance(cls, **kwargs: Any) -> "VisionOcrEngine":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    _instance: "VisionOcrEngine | None" = None

    def recognize(self, image: Any) -> list[dict]:
        require_vision_deps()
        import cv2
        import objc
        from Foundation import NSData
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest

        if image is None or getattr(image, "size", 0) == 0:
            return []

        h, w = image.shape[:2]
        ok, buf = cv2.imencode(".png", image)
        if not ok:
            return []

        ns_data = NSData.dataWithBytes_length_(buf.tobytes(), len(buf))
        handler = VNImageRequestHandler.alloc().initWithData_options_(ns_data, None)
        request = VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])
        request.setRecognitionLevel_(1)  # accurate

        err = objc.nil
        handler.performRequests_error_([request], err)

        lines: list[dict] = []
        observations = request.results() or []
        for obs in observations:
            candidates = obs.topCandidates_(1)
            if not candidates:
                continue
            cand = candidates[0]
            conf = float(cand.confidence())
            if conf < self.min_confidence:
                continue
            text = str(cand.string()).strip()
            if not text:
                continue
            bbox = obs.boundingBox()
            x = float(bbox.origin.x) * w
            y = (1.0 - float(bbox.origin.y) - float(bbox.size.height)) * h
            bw = float(bbox.size.width) * w
            bh = float(bbox.size.height) * h
            pixel_bbox = [
                [x, y],
                [x + bw, y],
                [x + bw, y + bh],
                [x, y + bh],
            ]
            lines.append({"text": text, "confidence": conf, "bbox": pixel_bbox})

        logger.debug("Vision OCR 识别 %d 行", len(lines))
        return lines
