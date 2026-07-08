"""Pexels 素材降级服务。"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from vplatform.config.schema import MaterialConfig


class MaterialFallbackService:
    PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"

    def __init__(self, config: MaterialConfig) -> None:
        self.config = config
        self._fail_count = 0

    def record_failure(self) -> None:
        self._fail_count += 1

    def should_fallback(self) -> bool:
        return self.config.enabled and self._fail_count >= self.config.fallback_after_failures

    def reset_failures(self) -> None:
        self._fail_count = 0

    def download_clip(self, query: str, output_dir: Path, duration_sec: float) -> Path | None:
        api_key = self._pick_api_key()
        if not api_key:
            logger.warning("未配置 Pexels API Key，无法素材降级")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        headers = {"Authorization": api_key}
        params = {"query": query, "per_page": 5, "orientation": "landscape"}

        try:
            resp = requests.get(self.PEXELS_VIDEO_SEARCH, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
        except requests.RequestException as exc:
            logger.error("Pexels 搜索失败: {}", exc)
            return None

        if not videos:
            return None

        video = random.choice(videos)
        files = sorted(video.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
        if not files:
            return None

        url = files[0]["link"]
        raw_path = output_dir / f"pexels_{video['id']}.mp4"
        trimmed_path = output_dir / f"pexels_{video['id']}_trim.mp4"

        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                raw_path.write_bytes(r.content)
            self._trim(raw_path, trimmed_path, duration_sec)
            logger.info("素材降级成功 query={} path={}", query, trimmed_path)
            return trimmed_path
        except (requests.RequestException, RuntimeError) as exc:
            logger.error("素材下载失败: {}", exc)
            return None

    def _pick_api_key(self) -> str | None:
        keys = [k for k in self.config.pexels_api_keys if k]
        if not keys:
            import os

            env_key = os.getenv("PEXELS_API_KEY", "")
            return env_key or None
        return random.choice(keys)

    @staticmethod
    def _trim(src: Path, dest: Path, duration_sec: float) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-an",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
