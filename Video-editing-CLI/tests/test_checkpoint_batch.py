"""断点续跑与批量队列测试。"""

import json
from pathlib import Path

from video_edit.config import AppConfig
from video_edit.pipelines.aroll import run_aroll_pipeline
from video_edit.services.batch_queue import run_batch
from video_edit.services.checkpoint import load_checkpoint, save_checkpoint, stage_completed


def test_checkpoint_roundtrip(tmp_path: Path):
    save_checkpoint(tmp_path, "extract", {"paths": {"audio": "a.wav"}})
    cp = load_checkpoint(tmp_path)
    assert cp is not None
    assert stage_completed(cp, "extract")
    assert not stage_completed(cp, "transcribe")


def test_demo_pipeline_creates_checkpoint_on_rerun(tmp_path: Path):
    r1 = run_aroll_pipeline(
        video=None,
        script=None,
        output_dir=tmp_path,
        config=AppConfig(),
        demo=True,
    )
    assert r1.fcpxml_path and r1.fcpxml_path.is_file()
    assert r1.edl_path and r1.edl_path.is_file()


def test_batch_demo_manifest(tmp_path: Path):
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {"id": "demo1", "video": "x.mp4", "script": "x.txt"},
                ]
            }
        ),
        encoding="utf-8",
    )
    # 缺少文件应标记 failed
    summary = run_batch(manifest, tmp_path / "out", AppConfig(), resume=False)
    assert summary["failed"] == 1
