"""静音区间检测（ffmpeg silencedetect）。"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from loguru import logger

from video_edit.services.audio import require_ffmpeg


@dataclass(frozen=True)
class SilenceRegion:
    start: float
    end: float
    duration: float


_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


def detect_silence_regions(
    audio_path: str,
    *,
    threshold_db: float = -40.0,
    min_duration_sec: float = 0.3,
) -> list[SilenceRegion]:
    """用 ffmpeg silencedetect 检测静音段。"""
    ffmpeg = require_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-i",
        audio_path,
        "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_duration_sec}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("silencedetect 失败: {}", (result.stderr or "")[-500:])
        return []

    regions: list[SilenceRegion] = []
    pending_start: float | None = None
    for line in (result.stderr or "").splitlines():
        m_start = _SILENCE_START.search(line)
        if m_start:
            pending_start = float(m_start.group(1))
            continue
        m_end = _SILENCE_END.search(line)
        if m_end and pending_start is not None:
            end = float(m_end.group(1))
            duration = float(m_end.group(2))
            regions.append(SilenceRegion(start=pending_start, end=end, duration=duration))
            pending_start = None

    logger.debug("检测到 {} 段静音", len(regions))
    return regions


def is_in_silence(t: float, silences: list[SilenceRegion], margin: float = 0.05) -> bool:
    for s in silences:
        if s.start - margin <= t <= s.end + margin:
            return True
    return False


def snap_to_silence_boundary(
    t: float,
    silences: list[SilenceRegion],
    *,
    direction: str = "nearest",
) -> float:
    """将时间点吸附到最近的静音边界，便于切点落在自然气口。"""
    if not silences:
        return t
    best = t
    best_dist = float("inf")
    for s in silences:
        for candidate in (s.start, s.end):
            if direction == "before" and candidate > t:
                continue
            if direction == "after" and candidate < t:
                continue
            dist = abs(candidate - t)
            if dist < best_dist:
                best_dist = dist
                best = candidate
    if best_dist <= 0.35:
        return best
    return t
