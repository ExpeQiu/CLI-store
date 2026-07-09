"""批量任务队列。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from video_edit.config import AppConfig
from video_edit.pipelines.aroll import run_aroll_pipeline


@dataclass
class BatchJob:
    id: str
    video: str
    script: str
    status: str = "pending"
    output_dir: str | None = None
    error: str | None = None


@dataclass
class BatchManifest:
    jobs: list[BatchJob] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> BatchManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs = [
            BatchJob(
                id=j.get("id") or f"job_{i+1}",
                video=j["video"],
                script=j["script"],
                status=j.get("status", "pending"),
                output_dir=j.get("output_dir"),
                error=j.get("error"),
            )
            for i, j in enumerate(data.get("jobs", []))
        ]
        return cls(jobs=jobs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs": [
                {
                    "id": j.id,
                    "video": j.video,
                    "script": j.script,
                    "status": j.status,
                    "output_dir": j.output_dir,
                    "error": j.error,
                }
                for j in self.jobs
            ]
        }


def save_batch_state(manifest_path: Path, manifest: BatchManifest, stats: dict[str, Any]) -> None:
    state_path = manifest_path.with_suffix(".state.json")
    payload = {"manifest": manifest.to_dict(), "stats": stats, "updated_at": time.time()}
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_batch_state(manifest_path: Path) -> dict[str, Any] | None:
    state_path = manifest_path.with_suffix(".state.json")
    if not state_path.is_file():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def run_batch(
    manifest_path: Path,
    output_root: Path,
    config: AppConfig,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    manifest = BatchManifest.from_file(manifest_path)
    if resume:
        state = load_batch_state(manifest_path)
        if state and state.get("manifest"):
            for i, saved in enumerate(state["manifest"]["jobs"]):
                if i < len(manifest.jobs):
                    manifest.jobs[i].status = saved.get("status", manifest.jobs[i].status)
                    manifest.jobs[i].output_dir = saved.get("output_dir")
                    manifest.jobs[i].error = saved.get("error")

    results: list[dict[str, Any]] = []
    completed = 0
    failed = 0
    t0 = time.time()
    batch_dir = output_root / f"batch_{manifest_path.stem}"

    for job in manifest.jobs:
        if job.status == "completed":
            completed += 1
            results.append({"id": job.id, "status": "completed", "output_dir": job.output_dir, "skipped": True})
            continue

        video = Path(job.video).expanduser()
        script = Path(job.script).expanduser()
        if not video.is_file() or not script.is_file():
            job.status = "failed"
            job.error = f"文件不存在: video={video} script={script}"
            failed += 1
            results.append({"id": job.id, "status": "failed", "error": job.error})
            continue

        job.status = "running"
        save_batch_state(manifest_path, manifest, {"running": job.id})

        work_dir = batch_dir / job.id
        can_resume = resume and (work_dir / "checkpoint.json").is_file()

        try:
            logger.info("[batch] 开始 job={} video={} resume={}", job.id, video.name, can_resume)
            pipeline_result = run_aroll_pipeline(
                video=video,
                script=script,
                output_dir=batch_dir,
                config=config,
                fixed_job_id=job.id,
                work_dir=work_dir if can_resume else None,
                resume=can_resume,
            )
            job.status = "completed"
            job.output_dir = str(pipeline_result.output_dir)
            completed += 1
            results.append(
                {
                    "id": job.id,
                    "status": "completed",
                    "output_dir": job.output_dir,
                    "summary": pipeline_result.summary,
                }
            )
        except Exception as exc:
            logger.exception("[batch] job={} 失败", job.id)
            job.status = "failed"
            job.error = str(exc)
            failed += 1
            results.append({"id": job.id, "status": "failed", "error": job.error})

        save_batch_state(
            manifest_path,
            manifest,
            {"completed": completed, "failed": failed, "last_job": job.id},
        )

    summary = {
        "total": len(manifest.jobs),
        "completed": completed,
        "failed": failed,
        "elapsed_sec": round(time.time() - t0, 2),
        "results": results,
    }
    save_batch_state(manifest_path, manifest, summary)
    return summary
