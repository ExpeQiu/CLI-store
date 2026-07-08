"""ComfyUI API 服务 — 从 scripts/comfyapi.py 迁移并增强。"""

from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests
from loguru import logger


class ComfyUIError(Exception):
    """ComfyUI API 调用异常。"""


ProgressCallback = Callable[[str, float], None]


class ComfyUIAPI:
    def __init__(
        self,
        endpoint: str | None = None,
        timeout: int = 30,
        client_id: str | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        import os

        self.endpoint = (endpoint or os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188")).rstrip("/")
        self.timeout = timeout
        self.client_id = client_id or str(uuid.uuid4())
        self.poll_interval = poll_interval
        self._object_info_cache: dict[str, Any] | None = None
        logger.debug("ComfyUIAPI endpoint={} client_id={}", self.endpoint, self.client_id)

    def _url(self, path: str) -> str:
        from urllib.parse import urljoin

        return urljoin(f"{self.endpoint}/", path.lstrip("/"))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = self._url(path)
        logger.debug("请求 {} {}", method, url)
        try:
            resp = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ComfyUIError(f"无法连接 ComfyUI: {self.endpoint}") from exc
        if not resp.ok:
            raise ComfyUIError(f"ComfyUI 返回错误 {resp.status_code}: {resp.text[:500]}")
        return resp

    def system_stats(self) -> dict[str, Any]:
        return self._request("GET", "/system_stats").json()

    def health_check(self) -> bool:
        try:
            self.system_stats()
            return True
        except ComfyUIError:
            return False

    def get_object_info(self, refresh: bool = False) -> dict[str, Any]:
        if refresh or self._object_info_cache is None:
            self._object_info_cache = self._request("GET", "/object_info").json()
        return self._object_info_cache

    def node_exists(self, class_type: str) -> bool:
        return class_type in self.get_object_info()

    def submit_workflow(
        self,
        workflow: dict[str, Any],
        extra_data: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "prompt": workflow,
            "client_id": self.client_id,
        }
        if extra_data:
            payload["extra_data"] = extra_data

        data = self._request("POST", "/prompt", json=payload).json()
        if "error" in data:
            raise ComfyUIError(f"工作流提交失败: {data['error']}")
        if data.get("node_errors"):
            raise ComfyUIError(f"节点错误: {json.dumps(data['node_errors'], ensure_ascii=False)}")

        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"未返回 prompt_id: {data}")
        logger.info("工作流已提交 prompt_id={}", prompt_id)
        return prompt_id

    def get_history(self, prompt_id: str) -> dict[str, Any] | None:
        data = self._request("GET", f"/history/{prompt_id}").json()
        return data.get(prompt_id)

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout: int = 1800,
        poll_interval: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        interval = poll_interval if poll_interval is not None else self.poll_interval
        start = time.time()
        logger.info("等待任务完成 prompt_id={} timeout={}s", prompt_id, timeout)

        while time.time() - start < timeout:
            history = self.get_history(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise ComfyUIError(f"生成失败: {messages}")
                if history.get("outputs"):
                    elapsed = time.time() - start
                    logger.info("任务完成 prompt_id={} 耗时={:.1f}s", prompt_id, elapsed)
                    if on_progress:
                        on_progress(prompt_id, 1.0)
                    return history

            elapsed = time.time() - start
            if on_progress:
                on_progress(prompt_id, min(elapsed / timeout, 0.99))
            logger.debug("任务进行中 prompt_id={} elapsed={:.0f}s", prompt_id, elapsed)
            time.sleep(interval)

        raise ComfyUIError(f"任务超时 ({timeout}s): prompt_id={prompt_id}")

    def get_output_files(self, prompt_id: str) -> list[dict[str, Any]]:
        history = self.get_history(prompt_id)
        if not history:
            return []

        files: list[dict[str, Any]] = []
        for node_id, node_output in history.get("outputs", {}).items():
            for key in ("images", "gifs", "videos"):
                for item in node_output.get(key, []):
                    files.append(
                        {
                            "node_id": node_id,
                            "type": key,
                            "filename": item.get("filename"),
                            "subfolder": item.get("subfolder", ""),
                            "type_hint": item.get("type", "output"),
                        }
                    )
        logger.info("提取输出文件 count={} prompt_id={}", len(files), prompt_id)
        return files

    def download_file(self, file_info: dict[str, Any], dest_dir: Path) -> Path:
        params = {
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder", ""),
            "type": file_info.get("type_hint", "output"),
        }
        resp = self._request("GET", "/view", params=params)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file_info["filename"]
        dest.write_bytes(resp.content)
        logger.info("文件已下载 {}", dest)
        return dest

    def upload_image(self, image_path: str | Path, subfolder: str = "", overwrite: bool = True) -> str:
        image_path = Path(image_path)
        if not image_path.exists():
            raise ComfyUIError(f"图片不存在: {image_path}")

        with image_path.open("rb") as f:
            files = {"image": (image_path.name, f, "application/octet-stream")}
            data = {"subfolder": subfolder, "type": "input", "overwrite": str(overwrite).lower()}
            result = self._request("POST", "/upload/image", files=files, data=data).json()

        uploaded_name = result.get("name", image_path.name)
        logger.info("图片已上传 name={}", uploaded_name)
        return uploaded_name


def load_workflow(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    logger.debug("加载工作流 {}", path)
    return data


def _flatten_model_options(value: Any) -> list[str]:
    """将 object_info 中的模型选项展平为字符串列表。"""
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


def workflow_models_available(api: ComfyUIAPI, workflow_data: dict[str, Any]) -> bool:
    """检查工作流引用的模型是否已在 ComfyUI 端部署。"""
    object_info = api.get_object_info()
    prompt = workflow_data.get("prompt", {})

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
                logger.warning(
                    "工作流模型不可用 class={} {}={} available={}",
                    class_type,
                    key,
                    model_name,
                    available[:5],
                )
                return False
    return True


def build_prompt(workflow_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """根据工作流定义和参数构建 ComfyUI API prompt。"""
    prompt = json.loads(json.dumps(workflow_data["prompt"]))
    inject_map: dict[str, list[str]] = workflow_data.get("inject", {})
    resolved = dict(params)

    if resolved.get("seed", -1) in (-1, None):
        resolved["seed"] = random.randint(0, 2**63 - 1)

    for key, node_path in inject_map.items():
        if key not in resolved:
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


class ComfyUIService:
    """高层 ComfyUI 服务 — 工作流执行封装。"""

    def __init__(
        self,
        root: Path,
        endpoint: str | None = None,
        timeout_sec: int = 1800,
        poll_interval: float = 5.0,
    ) -> None:
        self.root = root
        self.api = ComfyUIAPI(
            endpoint=endpoint,
            timeout=30,
            poll_interval=poll_interval,
        )
        self.timeout_sec = timeout_sec

    def health(self) -> dict[str, Any]:
        ok = self.api.health_check()
        result: dict[str, Any] = {"endpoint": self.api.endpoint, "healthy": ok}
        if ok:
            result["devices"] = self.api.system_stats().get("devices", [])
        return result

    def resolve_workflow_path(self, name: str) -> Path:
        from vplatform.workflows.registry import WorkflowRegistry

        return WorkflowRegistry(self.root).resolve(name)

    def workflow_ready(self, workflow_name: str) -> bool:
        """检查工作流所需节点与模型是否可用。"""
        workflow_path = self.resolve_workflow_path(workflow_name)
        workflow_data = load_workflow(workflow_path)
        for node in workflow_data.get("required_nodes", []):
            if not self.api.node_exists(node):
                logger.warning("工作流 {} 缺少节点 {}", workflow_name, node)
                return False
        if not workflow_models_available(self.api, workflow_data):
            logger.warning("工作流 {} 模型未就绪", workflow_name)
            return False
        return True

    def run_workflow(
        self,
        workflow_name: str,
        params: dict[str, Any],
        output_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> list[Path]:
        workflow_path = self.resolve_workflow_path(workflow_name)
        workflow_data = load_workflow(workflow_path)
        prompt = build_prompt(workflow_data, params)
        prompt_id = self.api.submit_workflow(prompt)
        self.api.wait_for_completion(
            prompt_id,
            timeout=self.timeout_sec,
            on_progress=on_progress,
        )
        files = self.api.get_output_files(prompt_id)
        if not files:
            raise ComfyUIError(f"未找到输出文件 prompt_id={prompt_id}")
        return [self.api.download_file(f, output_dir) for f in files]

    def t2i(
        self,
        positive_prompt: str,
        negative_prompt: str,
        output_dir: Path,
        workflow_name: str = "wan2.1_txt2img",
        profile: dict[str, Any] | None = None,
    ) -> Path:
        profile = profile or {}
        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            **profile,
        }
        paths = self.run_workflow(workflow_name, params, output_dir)
        return paths[0]

    def t2v(
        self,
        positive_prompt: str,
        negative_prompt: str,
        output_dir: Path,
        workflow_name: str = "wan2.1_txt2vid",
        profile: dict[str, Any] | None = None,
    ) -> Path:
        profile = profile or {}
        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            **profile,
        }
        paths = self.run_workflow(workflow_name, params, output_dir)
        return paths[0]

    def i2v(
        self,
        image_path: str | Path,
        motion_prompt: str,
        negative_prompt: str,
        duration_sec: float,
        output_dir: Path,
        workflow_name: str = "wan2.1_img2vid",
        profile: dict[str, Any] | None = None,
        fps: int = 16,
    ) -> Path:
        profile = profile or {}
        length = max(int(duration_sec * fps), 9)
        length = length + (length % 4)  # Wan 要求帧数为 4n+1
        if length % 4 != 1:
            length += 1

        uploaded = self.api.upload_image(image_path)
        params = {
            "positive_prompt": motion_prompt,
            "negative_prompt": negative_prompt,
            "image_name": uploaded,
            "length": length,
            "fps": fps,
            **profile,
        }
        try:
            paths = self.run_workflow(workflow_name, params, output_dir)
            return paths[0]
        except ComfyUIError:
            logger.warning("I2V 失败，降级为 T2V motion_prompt={}", motion_prompt[:60])
            combined = f"{motion_prompt}, based on keyframe image"
            return self.t2v(combined, negative_prompt, output_dir, profile=profile)
