"""Comfyui-CLI 根目录与配置发现。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from loguru import logger

_USER_CONFIG_DIR = Path.home() / ".comfyui"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.yaml"


def user_config_dir() -> Path:
    return _USER_CONFIG_DIR


def user_config_path() -> Path:
    return _USER_CONFIG_PATH


def _read_yaml_root(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("配置解析失败 path={} err={}", config_path, exc)
        return None
    if value := data.get("root"):
        return Path(str(value)).expanduser().resolve()
    return None


def _find_project_root_from_cwd(start: Path | None = None) -> Path | None:
    cwd = (start or Path.cwd()).resolve()
    for directory in (cwd, *cwd.parents):
        if (directory / "config.yaml").exists():
            return directory
        if (directory / "workflows").is_dir() and (directory / "pyproject.toml").exists():
            return directory
    return None


def _package_dev_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_comfyui_root(start: Path | None = None, explicit: Path | str | None = None) -> Path:
    """配置发现链：explicit → COMFYUI_ROOT → cwd 向上 → ~/.comfyui → 包开发根。"""
    if explicit:
        root = Path(explicit).expanduser().resolve()
        logger.debug("使用显式 root={}", root)
        return root

    if env_root := os.getenv("COMFYUI_ROOT"):
        root = Path(env_root).expanduser().resolve()
        logger.debug("使用 COMFYUI_ROOT={}", root)
        return root

    if project_root := _find_project_root_from_cwd(start):
        logger.debug("从工作目录发现项目 root={}", project_root)
        return project_root

    if _USER_CONFIG_PATH.exists():
        if home_root := _read_yaml_root(_USER_CONFIG_PATH):
            logger.debug("从 ~/.comfyui/config.yaml 读取 root={}", home_root)
            return home_root
        logger.debug("使用 ~/.comfyui 作为 root")
        return _USER_CONFIG_DIR

    dev_root = _package_dev_root()
    logger.debug("回退到包开发根 root={}", dev_root)
    return dev_root


def resolve_config_path(root: Path | None = None) -> tuple[Path, Path]:
    """返回 (comfyui_root, config_yaml_path)。"""
    resolved_root = resolve_comfyui_root(explicit=root)

    local_config = resolved_root / "config.yaml"
    if local_config.exists():
        return resolved_root, local_config

    if _USER_CONFIG_PATH.exists():
        if home_root := _read_yaml_root(_USER_CONFIG_PATH):
            resolved_root = home_root
        return resolved_root, _USER_CONFIG_PATH

    return resolved_root, local_config


def find_config_example(root: Path | None = None) -> Path | None:
    resolved = resolve_comfyui_root(explicit=root)
    for candidate in (
        resolved / "config.example.yaml",
        _package_dev_root() / "config.example.yaml",
    ):
        if candidate.exists():
            return candidate
    return None
