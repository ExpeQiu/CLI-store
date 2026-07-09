"""Multicam 波形同步测试。"""

import math
import shutil
import struct
import wave
from pathlib import Path

from video_edit.services.multicam import find_audio_offset, sync_multicam


def _write_chirp_wav(
    path: Path,
    *,
    prefix_silence_samples: int = 0,
    sr: int = 800,
    duration: int = 2000,
) -> None:
    """非周期 chirp，避免方波互相关多峰歧义。"""
    samples = [0] * prefix_silence_samples
    for i in range(duration):
        phase = 2 * math.pi * (80 + i * 0.35) * i / sr
        samples.append(int(8000 * math.sin(phase)))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def test_sync_same_file_near_zero_offset(tmp_path: Path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_chirp_wav(a)
    shutil.copy(a, b)
    result = sync_multicam(a, [b], sample_rate=800, max_lag_sec=0.5)
    assert len(result.cameras) == 1
    assert result.cameras[0].confidence > 0.5
    assert abs(result.cameras[0].offset_sec) < 0.05


def test_find_audio_offset_detects_delay(tmp_path: Path):
    sr = 800
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    delay_samples = 40  # 0.05s
    _write_chirp_wav(a, sr=sr)
    _write_chirp_wav(b, prefix_silence_samples=delay_samples, sr=sr)
    from video_edit.services.multicam import _extract_pcm_mono

    ref = _extract_pcm_mono(a, sr)
    other = _extract_pcm_mono(b, sr)
    offset, confidence = find_audio_offset(ref, other, sample_rate=sr, max_lag_sec=1.0)
    expected = -delay_samples / sr
    assert confidence > 0.5
    assert abs(offset - expected) < 0.02
