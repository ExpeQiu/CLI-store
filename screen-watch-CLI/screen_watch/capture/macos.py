"""macOS 窗口定位与截屏"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from screen_watch.config import RegionConfig
from screen_watch.utils.logger import setup_logger

logger = setup_logger()


@dataclass
class WindowInfo:
    title: str
    owner: str
    bounds: tuple[int, int, int, int]  # x, y, w, h (logical points)
    window_id: int | None = None

    @property
    def label(self) -> str:
        if self.title:
            return f"{self.owner} — {self.title}"
        return self.owner


def require_capture_deps() -> None:
    try:
        import mss  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "缺少截屏依赖，请执行: pip install -e '.[capture]'"
        ) from exc


def get_scale_factor() -> float:
    require_capture_deps()
    try:
        from AppKit import NSScreen

        return float(NSScreen.mainScreen().backingScaleFactor())
    except Exception:
        return 2.0


def is_window_frontmost(window: WindowInfo) -> bool:
    """前台应用是否与目标窗口所属 App 一致"""
    require_capture_deps()
    try:
        from AppKit import NSWorkspace

        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        front_name = front.localizedName() if front else ""
        return bool(front_name) and window.owner == front_name
    except Exception:
        return True


def _raw_windows() -> list[dict[str, Any]]:
    require_capture_deps()
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
    )

    return CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID,
    )


def _parse_window(raw: dict[str, Any]) -> WindowInfo | None:
    bounds = raw.get("kCGWindowBounds") or {}
    width = int(bounds.get("Width", 0))
    height = int(bounds.get("Height", 0))
    if width <= 0 or height <= 0:
        return None

    return WindowInfo(
        title=str(raw.get("kCGWindowName") or ""),
        owner=str(raw.get("kCGWindowOwnerName") or ""),
        bounds=(
            int(bounds.get("X", 0)),
            int(bounds.get("Y", 0)),
            width,
            height,
        ),
        window_id=int(raw.get("kCGWindowNumber", 0)) or None,
    )


def list_windows(title_filter: str = "") -> list[WindowInfo]:
    results: list[WindowInfo] = []
    needle = title_filter.strip().lower()

    for raw in _raw_windows():
        info = _parse_window(raw)
        if info is None:
            continue
        haystack = f"{info.owner} {info.title}".lower()
        if needle and needle not in haystack:
            continue
        results.append(info)

    results.sort(key=lambda w: w.bounds[2] * w.bounds[3], reverse=True)
    return results


def find_window(title_contains: str) -> WindowInfo | None:
    matches = list_windows(title_contains)
    if not matches:
        return None
    return matches[0]


def region_to_pixels(
    window: WindowInfo,
    region: RegionConfig,
    *,
    scale: float | None = None,
) -> dict[str, int]:
    scale = scale or get_scale_factor()
    wx, wy, ww, wh = window.bounds

    if region.mode == "relative":
        rx = wx + region.x * ww
        ry = wy + region.y * wh
        rw = region.w * ww
        rh = region.h * wh
    else:
        rx, ry, rw, rh = region.x, region.y, region.w, region.h

    return {
        "left": int(round(rx * scale)),
        "top": int(round(ry * scale)),
        "width": max(1, int(round(rw * scale))),
        "height": max(1, int(round(rh * scale))),
    }


def _grab_pixels(monitor: dict[str, int]) -> np.ndarray:
    import mss

    try:
        with mss.mss() as sct:
            shot = sct.grab(monitor)
            frame = np.array(shot)
            # BGRA -> BGR
            return frame[:, :, :3].copy()
    except Exception as exc:
        msg = str(exc).lower()
        if "permission" in msg or "capture" in msg:
            raise PermissionError(
                "屏幕录制权限未授予，请在 系统设置 → 隐私与安全性 → 屏幕录制 中允许终端/Cursor"
            ) from exc
        raise


def capture_window(window: WindowInfo, *, scale: float | None = None) -> np.ndarray:
    scale = scale or get_scale_factor()
    wx, wy, ww, wh = window.bounds
    monitor = {
        "left": int(round(wx * scale)),
        "top": int(round(wy * scale)),
        "width": max(1, int(round(ww * scale))),
        "height": max(1, int(round(wh * scale))),
    }
    logger.debug("capture window monitor=%s", monitor)
    return _grab_pixels(monitor)


def capture_region(
    window: WindowInfo,
    region: RegionConfig,
    *,
    scale: float | None = None,
) -> np.ndarray:
    monitor = region_to_pixels(window, region, scale=scale)
    logger.debug("capture region=%s monitor=%s", region.name, monitor)
    return _grab_pixels(monitor)


def save_window_screenshot(window: WindowInfo, path: str) -> str:
    import cv2

    image = capture_window(window)
    cv2.imwrite(path, image)
    return path
