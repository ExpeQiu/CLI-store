"""流水线断点续跑。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

STAGES_ORDER = ["extract", "transcribe", "align", "refine", "export"]


def save_checkpoint(work_dir: Path, stage: str, data: dict[str, Any]) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    cp_path = work_dir / "checkpoint.json"
    existing: dict[str, Any] = {}
    if cp_path.is_file():
        existing = json.loads(cp_path.read_text(encoding="utf-8"))
    stages_done: list[str] = existing.get("stages_done", [])
    if stage not in stages_done:
        stages_done.append(stage)
    payload = {
        "stages_done": stages_done,
        "last_stage": stage,
        "paths": {**existing.get("paths", {}), **data.get("paths", {})},
        "meta": {**existing.get("meta", {}), **data.get("meta", {})},
    }
    cp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("checkpoint 已保存: stage={}", stage)


def load_checkpoint(work_dir: Path) -> dict[str, Any] | None:
    cp_path = work_dir / "checkpoint.json"
    if not cp_path.is_file():
        return None
    return json.loads(cp_path.read_text(encoding="utf-8"))


def stage_completed(checkpoint: dict[str, Any] | None, stage: str) -> bool:
    if not checkpoint:
        return False
    return stage in checkpoint.get("stages_done", [])


def next_stage_after(checkpoint: dict[str, Any] | None) -> str | None:
    if not checkpoint:
        return STAGES_ORDER[0]
    done = set(checkpoint.get("stages_done", []))
    for stage in STAGES_ORDER:
        if stage not in done:
            return stage
    return None
