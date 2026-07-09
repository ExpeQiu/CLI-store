"""video_post 单元测试（不依赖 ComfyUI）。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vplatform.services.video_post import VideoPostService  # noqa: E402


@pytest.fixture
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def test_probe_duration_missing_file():
    svc = VideoPostService()
    assert svc.probe_duration("/nonexistent/video.mp4") == 3.0


def test_concat_single_clip(tmp_path, ffmpeg_available):
    if not ffmpeg_available:
        pytest.skip("ffmpeg 不可用")
    # 生成 1 秒测试视频
    src = tmp_path / "a.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "out.mp4"
    svc = VideoPostService()
    svc.concat_clips([src], out, fps=16, transition="fade")
    assert out.is_file()


def test_ken_burns_from_image(tmp_path, ffmpeg_available):
    if not ffmpeg_available:
        pytest.skip("ffmpeg 不可用")
    img = tmp_path / "frame.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=512x288",
            "-frames:v",
            "1",
            str(img),
        ],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "kb.mp4"
    svc = VideoPostService()
    svc.ken_burns_clip(img, 1.5, out, fps=16, zoom=1.05)
    assert out.is_file()
    assert svc.probe_duration(out) > 0.5
