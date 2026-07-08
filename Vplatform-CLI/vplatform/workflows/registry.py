"""工作流注册表 — 扫描 workflows/ 与 data/workflows/。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger



def _skip_workflow_path(path: Path) -> bool:
    """忽略 macOS 资源叉与隐藏文件。"""
    name = path.name
    return name.startswith("._") or name.startswith(".")


class WorkflowRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.builtin_dir = root / "workflows"
        self.data_dir = root / "data" / "workflows"

    def list_workflows(self) -> list[str]:
        names: set[str] = set()
        for directory in (self.builtin_dir, self.data_dir):
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                if _skip_workflow_path(path):
                    continue
                names.add(path.stem)
        return sorted(names)

    def resolve(self, name: str) -> Path:
        if name.endswith(".json"):
            name = name[:-5]

        data_path = self.data_dir / f"{name}.json"
        if data_path.exists():
            logger.debug("工作流来自 data/ {}", data_path)
            return data_path

        builtin_path = self.builtin_dir / f"{name}.json"
        if builtin_path.exists():
            return builtin_path

        raise FileNotFoundError(f"工作流不存在: {name} (已搜索 data/ 与 workflows/)")
