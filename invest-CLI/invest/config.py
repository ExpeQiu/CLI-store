"""配置加载：CLI 参数 > 环境变量 > ~/.invest/config.yaml > 默认值"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from invest_core.paths import get_config_dir, get_data_dir, get_state_dir

CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "state_dir": str(get_state_dir()),
    "data_dir": str(get_data_dir()),
    "feishu": {
        "app_id": "",
        "app_secret_env": "FEISHU_APP_SECRET",
    },
    "mock_mode": False,
}


def is_mock_mode(cli_demo: bool = False) -> bool:
    if cli_demo:
        return True
    if os.environ.get("INVEST_MOCK_MODE", "").lower() in ("1", "true", "yes"):
        return True
    cfg = load_config()
    return bool(cfg.get("mock_mode"))


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def init_config() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            yaml.dump(DEFAULT_CONFIG, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
    return CONFIG_FILE
