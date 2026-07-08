"""配置序列化"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from screen_watch.config import AppConfig, RegionConfig


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    regions: dict[str, Any] = {}
    for name, region in config.regions.items():
        regions[name] = {
            "mode": region.mode,
            "x": region.x,
            "y": region.y,
            "w": region.w,
            "h": region.h,
            "preprocess": region.preprocess,
            "extract": region.extract,
            "diff": region.diff,
            "filter": region.filter,
            "parse": region.parse,
        }
    return {
        "preset": config.preset,
        "window": {"title_contains": config.window_title},
        "capture": {"interval_sec": config.interval_sec},
        "regions": regions,
    }


def save_config(config: AppConfig, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_to_dict(config), f, allow_unicode=True, sort_keys=False)
    return out
