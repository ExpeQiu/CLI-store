"""配置与环境变量"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SCRAPLING_CANDIDATES = (
    "/opt/homebrew/bin/scrapling",
    "/usr/local/bin/scrapling",
)


def get_scrapling_bin() -> str | None:
    """探测 scrapling 可执行文件路径"""
    env_path = os.environ.get("SCRAPLING_BIN")
    if env_path and os.path.isfile(env_path):
        return env_path
    for path in SCRAPLING_CANDIDATES:
        if os.path.isfile(path):
            return path
    return shutil.which("scrapling")


def get_cache_dir() -> Path:
    """HTML 缓存目录"""
    cache = Path(os.environ.get("CLAUTO_CACHE_DIR", Path.home() / ".clauto" / "cache"))
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_tavily_key() -> str | None:
    return os.environ.get("TAVILY_API_KEY")
