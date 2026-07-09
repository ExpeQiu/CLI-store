"""EDL 导出测试。"""

from pathlib import Path

from video_edit.config import AlignConfig, PipelineConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT
from video_edit.services.align import align_script_to_transcript
from video_edit.services.edl import export_edl


def test_export_edl(tmp_path: Path):
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(match_threshold=0.5),
        pipeline_config=PipelineConfig(),
    )
    video = tmp_path / "source.mp4"
    video.write_bytes(b"")
    out = tmp_path / "timeline.edl"
    export_edl(decision, video, out)
    text = out.read_text(encoding="utf-8")
    assert "TITLE:" in text
    assert "001" in text
