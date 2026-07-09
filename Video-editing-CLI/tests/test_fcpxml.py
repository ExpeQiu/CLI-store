"""FCPXML 导出测试。"""

from pathlib import Path

from video_edit.config import AlignConfig, ExportConfig, PipelineConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT
from video_edit.services.align import align_script_to_transcript
from video_edit.services.fcpxml import export_fcpxml


def test_export_fcpxml_structure(tmp_path: Path):
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(),
        pipeline_config=PipelineConfig(),
    )
    video = tmp_path / "source.mp4"
    video.write_bytes(b"")
    out = tmp_path / "timeline.fcpxml"
    export_fcpxml(
        decision,
        video,
        out,
        pipeline_config=PipelineConfig(),
        export_config=ExportConfig(),
    )
    text = out.read_text(encoding="utf-8")
    assert "fcpxml" in text
    assert "asset-clip" in text
    assert "r2" in text
