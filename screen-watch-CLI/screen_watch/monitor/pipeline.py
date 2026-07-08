"""区域 OCR 流水线"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from screen_watch.capture import WindowInfo, capture_region, capture_window
from screen_watch.capture.preprocess import apply_preprocess
from screen_watch.config import AppConfig, RegionConfig
from screen_watch.ocr.factory import OcrBackend, get_ocr_engine
from screen_watch.parsers.wechat_live import (
    ChatDiffState,
    ocr_lines_to_sorted_rows,
    ocr_lines_to_text,
    parse_chat_line,
    parse_viewer_count,
)
from screen_watch.utils.logger import setup_logger

logger = setup_logger()
TZ_CN = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(TZ_CN).isoformat()


class RegionPipeline:
    def __init__(
        self,
        config: AppConfig,
        ocr=None,
        *,
        ocr_backend: OcrBackend = "auto",
    ) -> None:
        self.config = config
        self.ocr = ocr or get_ocr_engine(ocr_backend)
        chat_region = config.regions.get("chat")
        dedup = 500
        if chat_region and chat_region.diff:
            dedup = int(chat_region.diff.get("dedup_window", 500))
        self.chat_state = ChatDiffState(dedup_window=dedup)
        self.last_viewer_count = 0

    def _ocr_region(self, window: WindowInfo, region: RegionConfig) -> tuple[list[dict], Any]:
        image = capture_region(window, region)
        processed = apply_preprocess(image, region.preprocess)
        return self.ocr.recognize(processed), processed

    def capture_region_once(
        self,
        window: WindowInfo,
        region_name: str,
        *,
        save_crop: str | None = None,
    ) -> dict[str, Any]:
        if region_name == "full":
            image = capture_window(window)
            lines = self.ocr.recognize(image)
            if save_crop:
                from screen_watch.capture.preprocess import save_debug_image
                save_debug_image(image, save_crop)
            return {
                "region": "full",
                "text": ocr_lines_to_text(lines),
                "lines": lines,
                "window": window.label,
                "bounds": window.bounds,
                "engine": getattr(self.ocr, "name", "unknown"),
            }

        region = self.config.regions.get(region_name)
        if region is None:
            raise ValueError(f"未知区域: {region_name}，可用: {list(self.config.regions)}")

        lines, processed = self._ocr_region(window, region)
        if save_crop:
            from screen_watch.capture.preprocess import save_debug_image
            save_debug_image(processed, save_crop)
        return {
            "region": region_name,
            "text": ocr_lines_to_text(lines),
            "lines": lines,
            "window": window.label,
            "bounds": window.bounds,
            "engine": getattr(self.ocr, "name", "unknown"),
        }

    def process_viewer(self, window: WindowInfo) -> dict[str, Any] | None:
        region = self.config.regions.get("viewer_count")
        if region is None:
            return None

        lines, _ = self._ocr_region(window, region)
        text = ocr_lines_to_text(lines)
        pattern = region.extract.get(
            "pattern",
            r"(\d+(?:\.\d+)?万?)人(?:看过|观看|在线)",
        )
        parsed = parse_viewer_count(text, pattern)
        if not parsed:
            logger.debug("viewer OCR 未匹配: %r", text[:120])
            return None

        parsed["ts"] = _now_iso()
        if lines:
            parsed["confidence"] = max(item["confidence"] for item in lines)
        self.last_viewer_count = parsed["viewer_count"]
        return parsed

    def process_chat(self, window: WindowInfo) -> list[dict[str, Any]]:
        region = self.config.regions.get("chat")
        if region is None:
            return []

        lines, _ = self._ocr_region(window, region)
        rows = ocr_lines_to_sorted_rows(lines)
        new_rows = self.chat_state.diff_lines(rows)

        drop_prefixes = list(region.filter.get("drop_prefixes", []))
        drop_contains = list(region.filter.get("drop_contains", []))

        events: list[dict[str, Any]] = []
        for row in new_rows:
            parsed = parse_chat_line(
                row,
                drop_prefixes=drop_prefixes,
                drop_contains=drop_contains,
            )
            if not parsed:
                continue
            parsed["ts"] = _now_iso()
            events.append(parsed)

        if events:
            logger.info("chat +%d lines", len(events))
        return events
