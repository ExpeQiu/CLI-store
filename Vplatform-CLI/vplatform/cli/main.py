"""Vplatform 开放 CLI — 统一入口。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from vplatform import __version__
from vplatform.cli.output import emit, emit_error
from vplatform.config.manager import ConfigManager, set_project_root
from vplatform.config.root import (
    find_config_example,
    resolve_vplatform_root,
    user_config_dir,
    user_config_path,
)
from vplatform.core import VplatformCore
from vplatform.models.task import STOP_AT_STAGES
from vplatform.workflows.registry import WorkflowRegistry

TOP_LEVEL_COMMANDS = frozenset(
    {
        "init",
        "health",
        "config",
        "pipeline",
        "task",
        "workflow",
        "status",
    }
)


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level.upper())


def _core(args: argparse.Namespace) -> VplatformCore:
    root = getattr(args, "root", None)
    if root:
        set_project_root(root)
    return VplatformCore(root=resolve_vplatform_root(explicit=root))


def _record_exit_code(record: Any) -> int:
    stage = record.stage.value if hasattr(record.stage, "value") else str(record.stage)
    return 0 if record.error is None and stage != "failed" else 1


def cmd_init(args: argparse.Namespace) -> int:
    home = user_config_dir()
    home.mkdir(parents=True, exist_ok=True)
    config_path = user_config_path()

    if config_path.exists() and not args.force:
        return emit_error(f"配置已存在: {config_path}，使用 --force 覆盖")

    example = find_config_example()
    if not example:
        return emit_error("未找到 config.example.yaml")

    data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    project_root = args.project_root or resolve_vplatform_root()
    if args.cwd or not args.project_root:
        cwd_root = _find_init_root()
        if cwd_root:
            project_root = cwd_root
    data["root"] = str(Path(project_root).resolve())

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    for sub in ("workflows", "prompts", "bgm"):
        (home / "data" / sub).mkdir(parents=True, exist_ok=True)

    emit(
        {
            "status": "ok",
            "config": str(config_path),
            "root": data["root"],
            "message": "已初始化 ~/.vplatform，可通过 vplatform health 验证环境",
        }
    )
    return 0


def _find_init_root() -> Path | None:
    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        if (directory / "config.yaml").exists():
            return directory
        if (directory / "workflows").is_dir() and (directory / "pyproject.toml").exists():
            return directory
    return cwd


def cmd_health(args: argparse.Namespace) -> int:
    core = _core(args)
    emit(core.health())
    return 0


def cmd_config_validate(args: argparse.Namespace) -> int:
    root = resolve_vplatform_root(explicit=getattr(args, "root", None))
    manager = ConfigManager(root=root)
    try:
        config = manager.load(reload=True)
    except Exception as exc:  # noqa: BLE001
        return emit_error(f"配置校验失败: {exc}")

    registry = WorkflowRegistry(root)
    workflows = registry.list_workflows()
    emit(
        {
            "status": "ok",
            "root": str(root),
            "config_path": str(manager.config_path),
            "workflows": workflows,
            "stop_at_default": config.pipeline.stop_at_default,
        }
    )
    return 0


def cmd_pipeline_run(args: argparse.Namespace) -> int:
    if not args.subject and not args.storyboard_file:
        return emit_error("请提供 --subject/-t 或 --storyboard-file")
    core = _core(args)
    record = core.run_pipeline(
        subject=args.subject or "",
        stop_at=args.stop_at,
        profile=args.profile,
        storyboard_file=args.storyboard_file,
        task_id=args.task_id,
    )
    emit(record.model_dump())
    return _record_exit_code(record)


def cmd_task(args: argparse.Namespace) -> int:
    core = _core(args)
    if args.task_action == "list":
        tasks = core.tasks.list_tasks()
        emit([t.model_dump() for t in tasks])
        return 0
    if not args.task_id:
        return emit_error("请提供 task_id")
    if args.task_action == "status":
        record = core.tasks.get(args.task_id) or core.tasks.load_persisted(args.task_id)
        if not record:
            return emit_error(f"任务不存在: {args.task_id}")
        emit(record.model_dump())
        return 0
    if args.task_action == "cancel":
        try:
            record = core.tasks.cancel(args.task_id)
        except KeyError:
            return emit_error(f"任务不存在: {args.task_id}")
        emit(record.model_dump())
        return 0
    return emit_error(f"未知 task 操作: {args.task_action}")


def cmd_workflow_list(args: argparse.Namespace) -> int:
    root = resolve_vplatform_root(explicit=getattr(args, "root", None))
    registry = WorkflowRegistry(root)
    emit({"root": str(root), "workflows": registry.list_workflows()})
    return 0


def cmd_workflow_validate(args: argparse.Namespace) -> int:
    root = resolve_vplatform_root(explicit=getattr(args, "root", None))
    registry = WorkflowRegistry(root)
    try:
        path = registry.resolve(args.name)
    except FileNotFoundError as exc:
        return emit_error(str(exc))
    emit({"name": args.name, "path": str(path), "status": "ok"})
    return 0



def cmd_status(args: argparse.Namespace) -> int:
    from vplatform.services.comfyui import ComfyUIAPI

    root = resolve_vplatform_root(explicit=getattr(args, "root", None))
    endpoint = args.endpoint
    if not endpoint:
        core = VplatformCore(root=root)
        endpoint = core.config.comfyui.endpoint
    api = ComfyUIAPI(endpoint=endpoint)
    ok = api.health_check()
    payload: dict[str, Any] = {
        "endpoint": api.endpoint,
        "healthy": ok,
        "vplatform_root": str(root),
    }
    if ok:
        payload["devices"] = api.system_stats().get("devices", [])
    emit(payload)
    return 0 if ok else 1


def _add_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        help="Vplatform 项目根目录（默认自动发现）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vplatform",
        description="Vplatform 分镜驱动短视频编排 CLI",
    )
    parser.add_argument("--version", action="version", version=f"vplatform {__version__}")

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="日志级别",
    )
    _add_root_arg(parent)

    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", parents=[parent], help="初始化 ~/.vplatform 配置")
    init.add_argument("--project-root", help="绑定项目根目录（写入 config.root）")
    init.add_argument("--cwd", action="store_true", help="自动检测当前目录为 root")
    init.add_argument("--force", action="store_true", help="覆盖已有配置")
    init.set_defaults(handler=cmd_init)

    health = sub.add_parser("health", parents=[parent], help="健康检查")
    health.set_defaults(handler=cmd_health)

    config = sub.add_parser("config", parents=[parent], help="配置管理")
    config_sub = config.add_subparsers(dest="config_action", required=True)
    validate = config_sub.add_parser("validate", help="校验配置与工作流")
    validate.set_defaults(handler=cmd_config_validate)

    pipeline = sub.add_parser("pipeline", parents=[parent], help="分镜流水线")
    pipeline_sub = pipeline.add_subparsers(dest="pipeline_action", required=True)
    run = pipeline_sub.add_parser("run", help="运行流水线")
    run.add_argument("--subject", "-t", default="", help="视频主题/文案")
    run.add_argument("--storyboard-file", help="已有分镜 JSON")
    run.add_argument("--stop-at", choices=STOP_AT_STAGES, default=None)
    run.add_argument("--profile", choices=["default", "fast"], default=None)
    run.add_argument("--task-id", help="续跑任务 ID")
    run.set_defaults(handler=cmd_pipeline_run)

    task = sub.add_parser("task", parents=[parent], help="任务管理")
    task.add_argument("task_action", choices=["list", "status", "cancel"])
    task.add_argument("task_id", nargs="?", default=None)
    task.set_defaults(handler=cmd_task)

    workflow = sub.add_parser("workflow", parents=[parent], help="工作流管理")
    wf_sub = workflow.add_subparsers(dest="workflow_action", required=True)
    wf_list = wf_sub.add_parser("list", help="列出可用工作流")
    wf_list.set_defaults(handler=cmd_workflow_list)
    wf_validate = wf_sub.add_parser("validate", help="校验工作流文件")
    wf_validate.add_argument("name", help="工作流名称或 xxx.json")
    wf_validate.set_defaults(handler=cmd_workflow_validate)


    status = sub.add_parser("status", parents=[parent], help="ComfyUI 连通性检查")
    status.add_argument("--endpoint")
    status.set_defaults(handler=cmd_status)

    return parser


def _inject_shorthands(argv: list[str]) -> list[str]:
    """兼容 vplatform run -t ... 与 vplatform -t ... 简写。"""
    if len(argv) <= 1:
        return argv
    first = argv[1]
    if first in ("--version", "-V", "-h", "--help"):
        return argv
    if first in TOP_LEVEL_COMMANDS:
        return argv
    if first.startswith("-"):
        return [argv[0], "pipeline", "run", *argv[1:]]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = _inject_shorthands(argv or sys.argv)
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    _configure_logging(args.log_level)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
