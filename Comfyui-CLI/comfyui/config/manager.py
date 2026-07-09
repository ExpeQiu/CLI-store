"""配置单例管理器 — 支持 YAML + .env 映射。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from comfyui.config.root import resolve_comfyui_root, resolve_config_path
from comfyui.config.schema import ComfyuiConfig

_CONFIG: ComfyuiConfig | None = None
_ROOT: Path | None = None


def get_project_root(explicit: Path | str | None = None) -> Path:
    global _ROOT
    if explicit:
        return Path(explicit).expanduser().resolve()
    if _ROOT is not None:
        return _ROOT
    _ROOT = resolve_comfyui_root()
    return _ROOT


def set_project_root(root: Path | str | None) -> None:
    global _ROOT, _CONFIG
    _ROOT = Path(root).expanduser().resolve() if root else None
    _CONFIG = None


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    comfyui = data.setdefault("comfyui", {})
    if endpoint := os.getenv("COMFYUI_ENDPOINT"):
        comfyui["endpoint"] = endpoint
    if base_path := os.getenv("COMFYUI_BASE_PATH"):
        comfyui["base_path"] = base_path
    rh = data.setdefault("providers", {}).setdefault("runninghub", {})
    if api_key := os.getenv("RUNNINGHUB_API_KEY"):
        rh["api_key"] = api_key
        rh["enabled"] = True
    return data


class ConfigManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root, self.config_path = resolve_config_path(root)
        self._config: ComfyuiConfig | None = None

    def load(self, reload: bool = False) -> ComfyuiConfig:
        if self._config is not None and not reload:
            return self._config

        data: dict[str, Any] = {}
        if self.config_path.exists():
            with self.config_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            logger.debug("已加载配置 root={} path={}", self.root, self.config_path)
        else:
            from comfyui.config.root import find_config_example

            example = find_config_example(self.root)
            if example and example.exists():
                with example.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                logger.info("使用默认配置示例 {}", example)

        data = _apply_env_overrides(data)
        self._config = ComfyuiConfig.model_validate(data)
        return self._config

    def save(self, config: ComfyuiConfig | None = None) -> None:
        cfg = config or self.load()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg.model_dump(), f, allow_unicode=True, sort_keys=False)
        logger.info("配置已保存 {}", self.config_path)

    def update(self, patch: dict[str, Any]) -> ComfyuiConfig:
        current = self.load().model_dump()
        self._deep_merge(current, patch)
        self._config = ComfyuiConfig.model_validate(current)
        return self._config

    @staticmethod
    def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> None:
        for key, value in patch.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value


def get_config_manager(root: Path | None = None) -> ConfigManager:
    return ConfigManager(root=root)


def get_config(root: Path | None = None, reload: bool = False) -> ComfyuiConfig:
    global _CONFIG
    if _CONFIG is None or reload:
        _CONFIG = get_config_manager(root).load(reload=reload)
    return _CONFIG
