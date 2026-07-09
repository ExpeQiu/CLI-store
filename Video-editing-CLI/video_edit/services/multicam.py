"""多机位音频波形同步。"""

from __future__ import annotations

import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from video_edit.services.audio import require_ffmpeg


@dataclass
class CameraSync:
    camera_id: str
    path: str
    offset_sec: float
    confidence: float


@dataclass
class MulticamSyncMap:
    primary: str
    sample_rate: int
    cameras: list[CameraSync]

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "sample_rate": self.sample_rate,
            "cameras": [
                {
                    "camera_id": c.camera_id,
                    "path": c.path,
                    "offset_sec": round(c.offset_sec, 4),
                    "confidence": round(c.confidence, 4),
                }
                for c in self.cameras
            ],
        }


def _extract_pcm_mono(video_path: Path, sample_rate: int = 800) -> list[float]:
    """提取单声道 PCM 并归一化为 float 样本（低采样率用于互相关）。"""
    ffmpeg = require_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"提取音频失败: {video_path.name}")
    raw = proc.stdout
    if len(raw) < 4:
        return []
    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    peak = max(abs(s) for s in samples) or 1
    return [s / peak for s in samples]


def _correlate_at_lag(a: list[float], b: list[float], lag: int) -> float:
    if lag >= 0:
        a_slice = a[lag:]
        b_slice = b[: len(a_slice)]
    else:
        b_slice = b[-lag:]
        a_slice = a[: len(b_slice)]
    n = min(len(a_slice), len(b_slice))
    if n < 10:
        return 0.0
    dot = sum(a_slice[i] * b_slice[i] for i in range(n))
    norm_a = sum(x * x for x in a_slice) ** 0.5
    norm_b = sum(x * x for x in b_slice) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_audio_offset(
    primary_samples: list[float],
    other_samples: list[float],
    *,
    sample_rate: int,
    max_lag_sec: float = 30.0,
) -> tuple[float, float]:
    # 仅用前 10s 做互相关，降低长周期口播/循环信号的歧义
    window = min(len(primary_samples), len(other_samples), sample_rate * 10)
    a = primary_samples[:window]
    b = other_samples[:window]
    max_lag = int(max_lag_sec * sample_rate)
    best_lag = 0
    best_score = -1.0
    tie_eps = 1e-4
    for lag in range(-max_lag, max_lag + 1):
        score = _correlate_at_lag(a, b, lag)
        if score > best_score + tie_eps or (
            abs(score - best_score) <= tie_eps and abs(lag) < abs(best_lag)
        ):
            best_score = score
            best_lag = lag
    offset_sec = best_lag / sample_rate
    return offset_sec, max(0.0, min(1.0, best_score))


def sync_multicam(
    primary_video: Path,
    secondary_videos: list[Path],
    *,
    sample_rate: int = 800,
    max_lag_sec: float = 30.0,
) -> MulticamSyncMap:
    primary_video = primary_video.resolve()
    logger.info("Multicam 同步: primary={}", primary_video.name)
    primary_samples = _extract_pcm_mono(primary_video, sample_rate)

    cameras: list[CameraSync] = []
    for idx, sec_path in enumerate(secondary_videos):
        sec_path = sec_path.resolve()
        cam_id = f"cam_{idx + 2}"
        other_samples = _extract_pcm_mono(sec_path, sample_rate)
        offset, confidence = find_audio_offset(
            primary_samples,
            other_samples,
            sample_rate=sample_rate,
            max_lag_sec=max_lag_sec,
        )
        logger.info("  {} offset={:.3f}s confidence={:.2f}", cam_id, offset, confidence)
        cameras.append(
            CameraSync(
                camera_id=cam_id,
                path=str(sec_path),
                offset_sec=offset,
                confidence=confidence,
            )
        )

    return MulticamSyncMap(
        primary=str(primary_video),
        sample_rate=sample_rate,
        cameras=cameras,
    )


def save_sync_map(sync_map: MulticamSyncMap, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sync_map.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_sync_map(path: Path) -> MulticamSyncMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    cameras = [
        CameraSync(
            camera_id=c["camera_id"],
            path=c["path"],
            offset_sec=float(c["offset_sec"]),
            confidence=float(c.get("confidence", 1.0)),
        )
        for c in data.get("cameras", [])
    ]
    return MulticamSyncMap(
        primary=data["primary"],
        sample_rate=int(data.get("sample_rate", 800)),
        cameras=cameras,
    )
