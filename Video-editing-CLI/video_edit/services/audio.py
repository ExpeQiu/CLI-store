"""ffmpeg 音频提取。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from video_edit.utils.errors import DependencyError


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise DependencyError("未找到 ffmpeg，请先安装: brew install ffmpeg")
    return path


def extract_audio(
    video_path: Path,
    output_wav: Path,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    ffmpeg = require_ffmpeg()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        str(output_wav),
    ]
    logger.info("提取音频: {} -> {}", video_path.name, output_wav.name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg stderr: {}", result.stderr[-2000:] if result.stderr else "")
        raise RuntimeError(f"ffmpeg 提取音频失败 (code={result.returncode})")
    return output_wav


def probe_duration(media_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        require_ffmpeg()
        ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise DependencyError("未找到 ffprobe")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"无法解析时长: {result.stdout!r}") from exc
