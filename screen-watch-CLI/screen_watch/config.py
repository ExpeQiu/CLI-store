"""配置加载"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path.home() / ".screen-watch" / "config.yaml",
]


@dataclass
class RegionConfig:
    name: str
    mode: str = "relative"
    x: float = 0.0
    y: float = 0.0
    w: float = 0.1
    h: float = 0.1
    preprocess: list[str] = field(default_factory=list)
    extract: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)
    filter: dict[str, Any] = field(default_factory=dict)
    parse: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    preset: str = "wechat-live"
    window_title: str = "微信"
    interval_sec: float = 1.5
    regions: dict[str, RegionConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        window = data.get("window", {})
        capture = data.get("capture", {})
        regions_raw = data.get("regions", {})
        regions = {
            name: RegionConfig(name=name, **cfg)
            for name, cfg in regions_raw.items()
        }
        return cls(
            preset=data.get("preset", "wechat-live"),
            window_title=window.get("title_contains", "微信"),
            interval_sec=float(capture.get("interval_sec", 1.5)),
            regions=regions,
        )


def load_config(path: str | Path | None = None) -> AppConfig:
    if path:
        config_path = Path(path)
    else:
        env_path = os.environ.get("SCREEN_WATCH_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            config_path = next(
                (p for p in DEFAULT_CONFIG_PATHS if p.exists()),
                DEFAULT_CONFIG_PATHS[0],
            )

    if not config_path.exists():
        return AppConfig()

    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.from_dict(data)


def wechat_live_default() -> AppConfig:
    """内置 preset，无 config.yaml 时可用"""
    return AppConfig.from_dict(
        {
            "preset": "wechat-live",
            "window": {"title_contains": "微信"},
            "capture": {"interval_sec": 1.5},
            "regions": {
                "viewer_count": {
                    "mode": "relative",
                    "x": 0.02,
                    "y": 0.03,
                    "w": 0.18,
                    "h": 0.06,
                    "preprocess": ["grayscale", "scale_2x"],
                    "extract": {
                        "pattern": r"(\d+(?:\.\d+)?万?)人(?:看过|观看|在线)",
                    },
                },
                "chat": {
                    "mode": "relative",
                    "x": 0.68,
                    "y": 0.10,
                    "w": 0.30,
                    "h": 0.60,
                    "preprocess": ["grayscale"],
                    "diff": {"mode": "line", "dedup_window": 500},
                    "filter": {
                        "drop_prefixes": ["通知:", "系统:"],
                        "drop_contains": ["直播公约", "理性消费"],
                    },
                    "parse": {"mode": "colon_split"},
                },
            },
        }
    )
