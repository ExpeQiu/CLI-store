"""Demo 流水线测试。"""

from pathlib import Path

from video_edit.config import AppConfig
from video_edit.pipelines.aroll import run_aroll_pipeline


def test_demo_pipeline(tmp_path: Path):
    result = run_aroll_pipeline(
        video=None,
        script=None,
        output_dir=tmp_path,
        config=AppConfig(),
        demo=True,
    )
    assert result.fcpxml_path and result.fcpxml_path.is_file()
    assert result.decisions_path and result.decisions_path.is_file()
    assert result.transcript_path and result.transcript_path.is_file()
    assert result.summary.get("demo") is True
    assert result.summary.get("kept_clips", 0) >= 1
