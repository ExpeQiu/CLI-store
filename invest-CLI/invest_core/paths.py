"""invest_core 路径解析：CLI 参数 > 环境变量 > ~/.invest > ~/.hermes 回退"""

from __future__ import annotations

import os
from pathlib import Path


def get_config_dir() -> Path:
    if env := os.environ.get("INVEST_CONFIG_DIR"):
        return Path(env).expanduser()
    return Path.home() / ".invest"


def get_state_dir() -> Path:
    if env := os.environ.get("INVEST_STATE_DIR"):
        return Path(env).expanduser()
    new_dir = get_config_dir()
    hermes_dir = Path.home() / ".hermes" / "invest"
    if hermes_dir.exists() and not (new_dir / "invest_state.json").exists():
        return hermes_dir
    return new_dir


def get_state_file() -> Path:
    if env := os.environ.get("INVEST_STATE_FILE"):
        return Path(env).expanduser()
    return get_state_dir() / "invest_state.json"


def get_data_dir() -> Path:
    if env := os.environ.get("INVEST_DATA_DIR"):
        return Path(env).expanduser()
    new_dir = get_config_dir() / "data"
    hermes_dir = Path.home() / ".hermes" / "data" / "invest"
    if hermes_dir.exists() and not new_dir.exists():
        return hermes_dir
    return new_dir
