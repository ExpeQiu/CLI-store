"""工作流注册表 — 扫描 workflows/ 与 data/workflows/（支持子目录）。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from loguru import logger


def _skip_workflow_path(path: Path) -> bool:
    name = path.name
    return name.startswith("._") or name.startswith(".")


class WorkflowRegistry:
    def __init__(self, root: Path, workflows_dir: str = "workflows", data_dir: str = "data/workflows") -> None:
        self.root = root
        self.builtin_dir = root / workflows_dir
        self.data_dir = root / data_dir

    def _scan_dir(self, directory: Path) -> dict[str, Path]:
        found: dict[str, Path] = {}
        if not directory.exists():
            return found
        for path in directory.rglob("*.json"):
            if _skip_workflow_path(path):
                continue
            found[path.stem] = path
        return found

    def list_workflows(self) -> list[str]:
        names: set[str] = set()
        names.update(self._scan_dir(self.builtin_dir))
        names.update(self._scan_dir(self.data_dir))
        return sorted(names)

    def resolve(self, name: str) -> Path:
        if name.endswith(".json"):
            name = name[:-5]

        data_map = self._scan_dir(self.data_dir)
        if name in data_map:
            logger.debug("工作流来自 data/ {}", data_map[name])
            return data_map[name]

        builtin_map = self._scan_dir(self.builtin_dir)
        if name in builtin_map:
            return builtin_map[name]

        raise FileNotFoundError(f"工作流不存在: {name} (已搜索 data/ 与 workflows/)")

    def load(self, name: str) -> dict[str, Any]:
        with self.resolve(name).open(encoding="utf-8") as f:
            return json.load(f)

    def inspect(self, name: str) -> dict[str, Any]:
        data = self.load(name)
        inject = data.get("inject", {})
        inject_fields = {}
        defaults = data.get("defaults", {})
        for key, path in inject.items():
            inject_fields[key] = {
                "path": path,
                "default": defaults.get(key),
                "type": type(defaults.get(key)).__name__ if key in defaults else "unknown",
            }
        return {
            "name": name,
            "display_name": data.get("name", name),
            "category": data.get("category", _infer_category(name, data)),
            "capability": data.get("capability", ""),
            "source": data.get("source", "local"),
            "description": data.get("description", ""),
            "workflow_id": data.get("workflow_id"),
            "models": data.get("models", {}),
            "defaults": defaults,
            "inject": inject_fields,
            "required_nodes": data.get("required_nodes", []),
            "output_nodes": data.get("output_nodes", []),
            "path": str(self.resolve(name)),
        }

    def add(self, src: Path, name: str | None = None, category: str = "custom") -> Path:
        src = Path(src).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"工作流文件不存在: {src}")
        data = json.loads(src.read_text(encoding="utf-8"))
        stem = name or src.stem
        data.setdefault("category", category)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        dest = self.data_dir / f"{stem}.json"
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("工作流已注册 name={} path={}", stem, dest)
        return dest

    def copy_to_data(self, src: Path, name: str) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        dest = self.data_dir / f"{name}.json"
        shutil.copy2(src, dest)
        return dest


def _infer_category(name: str, data: dict[str, Any]) -> str:
    if data.get("category"):
        return str(data["category"])
    lower = name.lower()
    if "digital" in lower:
        return "digital"
    if any(k in lower for k in ("txt2vid", "img2vid", "video", "i2v", "t2v")):
        return "video"
    if any(k in lower for k in ("txt2img", "flux", "image", "t2i", "i2i")):
        return "image"
    return "custom"
