"""算力 Provider 路由 — autodl / local / commercial。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests
from loguru import logger

from vplatform.config.schema import ProviderConfig
from vplatform.services.comfyui import ComfyUIAPI


class ProviderRouter:
    def __init__(self, root: Path, config: ProviderConfig, local_endpoint: str) -> None:
        self.root = root
        self.config = config
        self.local_endpoint = local_endpoint
        self._active: str | None = None

    def select_endpoint(self) -> tuple[str, str]:
        """返回 (endpoint, provider_name)。"""
        for name in self.config.priority:
            if name == "autodl" and self._check_autodl():
                self._active = "autodl"
                logger.info("Provider 选择 autodl endpoint={}", self.local_endpoint)
                return self.local_endpoint, "autodl"
            if name == "local" and self._check_local():
                self._active = "local"
                logger.info("Provider 选择 local endpoint={}", self.local_endpoint)
                return self.local_endpoint, "local"
            if name == "commercial" and self.config.commercial_endpoint:
                if self._check_commercial():
                    self._active = "commercial"
                    logger.info("Provider 选择 commercial endpoint={}", self.config.commercial_endpoint)
                    return self.config.commercial_endpoint, "commercial"

        raise RuntimeError("无可用 ComfyUI Provider，请检查隧道或本地服务")

    @property
    def active_provider(self) -> str | None:
        return self._active

    def _check_local(self) -> bool:
        return ComfyUIAPI(endpoint=self.local_endpoint).health_check()

    def _autodl_script(self) -> Path | None:
        rel = (self.config.autodl_tunnel_script or "").strip()
        if not rel:
            return None
        script = self.root / rel
        return script if script.exists() else None

    def _check_autodl(self) -> bool:
        script = self._autodl_script()
        if script is not None:
            try:
                result = subprocess.run(
                    [str(script), "status"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=self.root,
                )
                if result.returncode != 0:
                    logger.debug("AutoDL 隧道未就绪 rc={}", result.returncode)
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("AutoDL status 检查失败: {}", exc)

        return self._check_local()

    def _check_commercial(self) -> bool:
        try:
            resp = requests.get(
                f"{self.config.commercial_endpoint.rstrip('/')}/system_stats",
                timeout=10,
            )
            return resp.ok
        except requests.RequestException:
            return False

    def ensure_tunnel(self) -> bool:
        script = self._autodl_script()
        if script is None:
            return False
        try:
            subprocess.run([str(script), "start"], check=False, timeout=30, cwd=self.root)
            return self._check_local()
        except (subprocess.TimeoutExpired, OSError):
            return False
