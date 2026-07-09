"""工作流加载与 prompt 构建。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from loguru import logger

from comfyui.core.api import ComfyUIAPI


def load_workflow(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    logger.debug("加载工作流 {}", path)
    return data


def _flatten_model_options(value: Any) -> list[str]:
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            return [str(item) for item in value[0]]
        return [str(item) for item in value]
    return []


def _model_input_keys(class_type: str) -> list[str]:
    mapping = {
        "UNETLoader": ["unet_name"],
        "CLIPLoader": ["clip_name"],
        "DualCLIPLoader": ["clip_name1", "clip_name2"],
        "VAELoader": ["vae_name"],
    }
    return mapping.get(class_type, [])


def workflow_models_available(api: ComfyUIAPI, workflow_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """检查工作流引用的模型是否已在 ComfyUI 端部署，返回 (就绪, 缺失列表)。"""
    if workflow_data.get("source") == "runninghub":
        return True, []

    try:
        object_info = api.get_object_info()
    except Exception:
        return False, ["comfyui_unreachable"]
    prompt = workflow_data.get("prompt", {})
    missing: list[str] = []

    for node in prompt.values():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        node_info = object_info.get(class_type, {}).get("input", {}).get("required", {})

        for key in _model_input_keys(class_type):
            model_name = inputs.get(key)
            if not model_name or not isinstance(model_name, str):
                continue
            available = _flatten_model_options(node_info.get(key, []))
            if model_name not in available:
                missing.append(f"{class_type}.{key}={model_name}")
                logger.warning(
                    "工作流模型不可用 class={} {}={}",
                    class_type,
                    key,
                    model_name,
                )
    return len(missing) == 0, missing


def check_required_nodes(api: ComfyUIAPI, workflow_data: dict[str, Any]) -> tuple[bool, list[str]]:
    if workflow_data.get("source") == "runninghub":
        return True, []
    try:
        missing = [node for node in workflow_data.get("required_nodes", []) if not api.node_exists(node)]
    except Exception:
        return False, workflow_data.get("required_nodes", [])
    return len(missing) == 0, missing


def build_prompt(workflow_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """根据工作流定义和参数构建 ComfyUI API prompt。"""
    if "prompt" not in workflow_data:
        raise ValueError(f"工作流 {workflow_data.get('name', '?')} 缺少 prompt 字段（云端桩不可本地执行）")

    prompt = json.loads(json.dumps(workflow_data["prompt"]))
    inject_map: dict[str, list[str]] = workflow_data.get("inject", {})
    resolved = dict(params)

    if resolved.get("seed", -1) in (-1, None):
        resolved["seed"] = random.randint(0, 2**63 - 1)

    for key, node_path in inject_map.items():
        if key not in resolved:
            continue
        if not isinstance(node_path, list):
            continue
        target: Any = prompt
        for part in node_path[:-1]:
            target = target[part]
        target[node_path[-1]] = resolved[key]

    output_nodes = workflow_data.get("output_nodes")
    if output_nodes:
        for node_id in output_nodes:
            if node_id in prompt:
                prompt[node_id].setdefault("_meta", {})["output"] = True

    return prompt


def merge_params(
    workflow_data: dict[str, Any],
    profile: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合并 defaults → profile → overrides；profile 仅覆盖工作流 inject 支持的字段。"""
    merged = dict(workflow_data.get("defaults", {}))
    inject_keys = set(workflow_data.get("inject", {}))
    if profile:
        for key, value in profile.items():
            if key in inject_keys or key in merged:
                merged[key] = value
    if overrides:
        merged.update(overrides)
    return merged
