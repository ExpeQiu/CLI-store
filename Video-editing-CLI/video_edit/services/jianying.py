"""剪映专业版工程元数据导出（调研阶段 — 非官方格式）。"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from video_edit.models.edit_decision import EditDecision


def export_jianying_metadata(
    decision: EditDecision,
    video_path: Path,
    output_path: Path,
    *,
    project_name: str = "A-Roll Edit",
) -> Path:
    """导出剪映可读的元数据 JSON（需手动导入素材并对照切点）。

    剪映工程为私有 draft 目录结构，暂无稳定公开 API。
    本文件提供：源媒体路径、保留片段列表、建议切点，供人工或后续插件使用。
    """
    payload = {
        "format": "video-edit-cli/jianying-metadata/v1",
        "note": "非官方剪映工程文件；请手动在剪映中导入 source_video 并按 clips 切点剪辑",
        "project_name": project_name,
        "source_video": str(video_path.resolve()),
        "frame_rate": decision.frame_rate,
        "total_output_sec": decision.total_output_sec,
        "clips": [
            {
                "id": c.id,
                "source_in_sec": c.source_in,
                "source_out_sec": c.source_out,
                "duration_sec": round(c.source_out - c.source_in, 3),
                "script_ref": c.script_ref,
            }
            for c in decision.keep_clips()
        ],
        "import_steps": [
            "1. 剪映专业版 → 导入 source_video",
            "2. 按 clips 中 source_in/source_out 手动标记切点",
            "3. 或使用 FCPXML/EDL 在达芬奇/FCP 完成初剪后回导",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("剪映元数据已导出: {}", output_path)
    return output_path
