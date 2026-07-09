#!/usr/bin/env python3
"""环境验证 — ComfyUI 连通性与工作流清单。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from comfyui.config.manager import ConfigManager
from comfyui.config.root import resolve_comfyui_root
from comfyui.core.api import ComfyUIAPI
from comfyui.core.registry import WorkflowRegistry
from comfyui.core.service import ComfyUIService


def main() -> int:
    root = resolve_comfyui_root()
    print(f"[+] root: {root}")

    manager = ConfigManager(root)
    config = manager.load()
    print(f"[+] config: {manager.config_path}")
    print(f"[+] endpoint: {config.comfyui.endpoint}")

    api = ComfyUIAPI(endpoint=config.comfyui.endpoint)
    ok = api.health_check()
    if ok:
        stats = api.system_stats()
        devices = stats.get("devices", [])
        gpu = devices[0].get("name", "unknown") if devices else "unknown"
        print(f"[+] ComfyUI: 就绪 ({gpu})")
    else:
        print("[!] ComfyUI: 未连接（本地生成命令将失败）")

    registry = WorkflowRegistry(root, config.workflows_dir, config.data_workflows_dir)
    workflows = registry.list_workflows()
    print(f"[+] 工作流: {len(workflows)} 个")
    for name in workflows:
        info = registry.inspect(name)
        print(f"    - {name} [{info.get('category')}/{info.get('capability')}] source={info.get('source')}")

    service = ComfyUIService(root, config)
    for name in workflows:
        ready, detail = service.workflow_status(name)
        status = "ready" if ready else "not_ready"
        extra = ""
        if detail.get("missing_nodes"):
            extra = f" missing_nodes={detail['missing_nodes']}"
        elif detail.get("missing_models"):
            extra = f" missing_models={detail['missing_models'][:2]}"
        elif detail.get("source") == "runninghub":
            extra = f" cloud_enabled={detail.get('cloud_enabled')}"
        elif detail.get("comfyui_healthy") is False:
            extra = " comfyui_offline"
        print(f"    [{status}] {name}{extra}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
