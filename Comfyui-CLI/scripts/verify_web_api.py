#!/usr/bin/env python3
"""Comfyui-CLI Web API 验证脚本 — 输出 JSON 日志便于排查。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("COMFYUI_CLI_ENDPOINT", "http://127.0.0.1:8765").rstrip("/")
POLL_INTERVAL = float(os.environ.get("COMFYUI_CLI_POLL_INTERVAL_SEC", "2"))
JOB_TIMEOUT = float(os.environ.get("COMFYUI_CLI_JOB_TIMEOUT_SEC", "120"))


def log(stage: str, **fields: Any) -> None:
    print(json.dumps({"stage": stage, "endpoint": BASE, **fields, "ts": int(time.time() * 1000)}))


def request_json(method: str, path: str, body: dict | None = None, timeout: float = 10) -> dict:
    url = f"{BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def poll_job(job_id: str) -> dict:
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        job = request_json("GET", f"/api/jobs/{job_id}")
        status = job.get("status")
        log("poll_job", job_id=job_id, status=status)
        if status in ("completed", "failed"):
            return job
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"任务超时 job_id={job_id}")


def main() -> int:
    try:
        ping = request_json("GET", "/api/ping")
        log("ping", ok=ping.get("ok"))
        if ping.get("ok") != "true":
            log("error", message="ping 失败")
            return 1

        health = request_json("GET", "/api/health")
        log("health_lite", healthy=health.get("healthy"), workflows_count=health.get("workflows_count"))
        if not health.get("healthy"):
            log("warn", message="ComfyUI 未就绪，跳过后续 job 验证")
            return 0

        workflows = request_json("GET", "/api/workflows?category=image")
        names = [w.get("name") for w in workflows.get("workflows", [])]
        log("workflows", count=len(names), names=names[:5])

        submitted = request_json(
            "POST",
            "/api/image/t2i",
            {"prompt": "verify web api red apple", "profile": "fast"},
            timeout=30,
        )
        job_id = submitted.get("job_id")
        if not job_id:
            log("error", message="t2i 未返回 job_id", response=submitted)
            return 1
        log("submit_t2i", job_id=job_id)

        job = poll_job(job_id)
        if job.get("status") != "completed":
            log("error", message=job.get("error", "job failed"), job=job)
            return 1

        result = job.get("result") or {}
        log(
            "completed",
            output_urls=result.get("output_urls"),
            output_absolute_urls=result.get("output_absolute_urls"),
            duration_sec=result.get("duration_sec"),
        )
        return 0
    except urllib.error.URLError as exc:
        log("error", message=f"无法连接 Web API: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        log("error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
