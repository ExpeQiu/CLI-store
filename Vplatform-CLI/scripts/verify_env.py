#!/usr/bin/env python3
"""CLI 环境验证 — vplatform 包、工作流、可选 ComfyUI 连通性。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def check_vplatform() -> list[str]:
    errors: list[str] = []
    print("\n[1/3] vplatform 包")
    try:
        from vplatform import __version__
        from vplatform.core import VplatformCore

        core = VplatformCore(root=PROJECT_ROOT)
        health = core.health()
        print(f"  [OK] VplatformCore version={health.get('version')} (__version__={__version__})")
        print(f"  [INFO] root={health.get('vplatform_root')}")
        wfs = health.get("workflows") or []
        print(f"  [INFO] workflows={len(wfs)}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vplatform 导入/初始化失败: {exc}")
        print(f"  [FAIL] {exc}")
    return errors


def check_workflow_files() -> list[str]:
    errors: list[str] = []
    print("\n[2/3] 工作流文件")
    required = ("flux_txt2img.json", "wan2.1_img2vid.json", "wan2.1_txt2img.json")
    for name in required:
        path = PROJECT_ROOT / "workflows" / name
        if path.is_file():
            print(f"  [OK] {name}")
        else:
            errors.append(f"缺少工作流: {path}")
            print(f"  [FAIL] 缺少 {name}")
    return errors


def check_comfyui(endpoint: str) -> list[str]:
    errors: list[str] = []
    print("\n[3/3] ComfyUI 连通性（可选）")
    from vplatform.services.comfyui import ComfyUIAPI, load_workflow

    api = ComfyUIAPI(endpoint=endpoint)
    if api.health_check():
        stats = api.system_stats()
        devices = stats.get("devices", [])
        print("  [OK] ComfyUI 可访问")
        if devices:
            print(f"  [INFO] 设备: {devices[0].get('name', 'unknown')}")
        wf_path = PROJECT_ROOT / "workflows" / "flux_txt2img.json"
        workflow = load_workflow(wf_path)
        for node in workflow.get("required_nodes", []):
            if api.node_exists(node):
                print(f"  [OK] 节点: {node}")
            else:
                errors.append(f"缺少节点: {node}")
                print(f"  [FAIL] 缺少节点: {node}")
    else:
        print(f"  [SKIP] ComfyUI 不可访问: {endpoint}")
        print("  [HINT] 启动 ComfyUI 后运行: vplatform status")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Vplatform-CLI 环境验证")
    parser.add_argument(
        "--require-comfyui",
        action="store_true",
        help="ComfyUI 不可用时视为失败",
    )
    args = parser.parse_args()

    endpoint = os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188")
    print("=== Vplatform-CLI 环境验证 ===")
    print(f"ComfyUI Endpoint: {endpoint}")

    errors: list[str] = []
    errors.extend(check_vplatform())
    errors.extend(check_workflow_files())

    comfy_errors = check_comfyui(endpoint)
    if args.require_comfyui:
        errors.extend(comfy_errors)
    elif comfy_errors:
        print("  [INFO] ComfyUI 检查项未强制（使用 --require-comfyui 强制）")

    print("\n=== 验证结果 ===")
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        print(f"\n失败 {len(errors)} 项。")
        return 1

    print("  ✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
