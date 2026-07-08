"""截屏模块"""

from __future__ import annotations

import sys

if sys.platform == "darwin":
    from screen_watch.capture.macos import (
        WindowInfo,
        capture_region,
        capture_window,
        find_window,
        get_scale_factor,
        list_windows,
        region_to_pixels,
        require_capture_deps,
        save_window_screenshot,
        is_window_frontmost,
    )
else:

    def require_capture_deps() -> None:
        raise RuntimeError("screen-watch 截屏目前仅支持 macOS")

    def list_windows(title_filter: str = "") -> list:
        require_capture_deps()
        return []

    def find_window(title_contains: str) -> None:
        require_capture_deps()

    def capture_region(*args, **kwargs):
        require_capture_deps()

    def capture_window(*args, **kwargs):
        require_capture_deps()

    def get_scale_factor() -> float:
        require_capture_deps()
        return 1.0

    def region_to_pixels(*args, **kwargs):
        require_capture_deps()

    class WindowInfo:  # noqa: D106 — stub for type hints on non-macOS
        pass


__all__ = [
    "WindowInfo",
    "capture_region",
    "capture_window",
    "find_window",
    "get_scale_factor",
    "list_windows",
    "region_to_pixels",
    "require_capture_deps",
    "save_window_screenshot",
    "is_window_frontmost",
]
