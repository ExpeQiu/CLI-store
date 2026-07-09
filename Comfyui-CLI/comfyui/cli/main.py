"""Comfyui-CLI 统一入口。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from comfyui import __version__
from comfyui.cli.output import emit, emit_error
from comfyui.config.manager import ConfigManager, get_config, set_project_root
from comfyui.config.root import find_config_example, resolve_comfyui_root, user_config_dir, user_config_path
from comfyui.core.registry import WorkflowRegistry
from comfyui.core.service import ComfyUIService
from comfyui.capabilities.digital import run_lip_sync, run_pipeline


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level.upper())


def _service(args: argparse.Namespace) -> ComfyUIService:
    root = getattr(args, "root", None)
    if root:
        set_project_root(root)
    resolved = resolve_comfyui_root(explicit=root)
    config = get_config(resolved, reload=True)
    return ComfyUIService(resolved, config)


def _parse_params(pairs: list[str] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not pairs:
        return params
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"参数格式错误: {pair}，应为 key=value")
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if value.lower() in ("true", "false"):
            params[key] = value.lower() == "true"
        else:
            try:
                if "." in value:
                    params[key] = float(value)
                else:
                    params[key] = int(value)
            except ValueError:
                params[key] = value
    return params


def _output_dir(args: argparse.Namespace, service: ComfyUIService) -> Path:
    if getattr(args, "output", None):
        return Path(args.output).expanduser().resolve()
    return service.root / service.config.output_dir


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
    project_root = args.project_root or resolve_comfyui_root()
    if args.cwd or not args.project_root:
        cwd_root = _find_init_root()
        if cwd_root:
            project_root = cwd_root
    data["root"] = str(Path(project_root).resolve())

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    for sub in ("workflows", "outputs", "logs"):
        (home / "data" / sub).mkdir(parents=True, exist_ok=True)

    emit(
        {
            "ok": True,
            "config": str(config_path),
            "root": data["root"],
            "message": "已初始化 ~/.comfyui，可通过 comfyui health 验证环境",
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
    service = _service(args)
    result = service.health()
    emit(result)
    return 0 if result.get("healthy") else 1


def cmd_status(args: argparse.Namespace) -> int:
    service = _service(args)
    endpoint = args.endpoint or service.config.comfyui.endpoint
    from comfyui.core.api import ComfyUIAPI

    api = ComfyUIAPI(endpoint=endpoint)
    ok = api.health_check()
    payload: dict[str, Any] = {
        "ok": ok,
        "endpoint": api.endpoint,
        "healthy": ok,
        "root": str(service.root),
        "workflows_count": len(service.registry.list_workflows()),
    }
    if ok:
        payload["devices"] = api.system_stats().get("devices", [])
    emit(payload)
    return 0 if ok else 1


def cmd_workflow_list(args: argparse.Namespace) -> int:
    service = _service(args)
    items = []
    for name in service.registry.list_workflows():
        info = service.registry.inspect(name)
        ready, detail = service.workflow_status(name)
        if args.category and info.get("category") != args.category:
            continue
        items.append({**info, "ready": ready, **detail})
    emit({"root": str(service.root), "workflows": items})
    return 0


def cmd_workflow_inspect(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        info = service.registry.inspect(args.name)
        ready, detail = service.workflow_status(args.name)
        emit({**info, "ready": ready, **detail})
        return 0
    except FileNotFoundError as exc:
        return emit_error(str(exc))


def cmd_workflow_validate(args: argparse.Namespace) -> int:
    service = _service(args)
    names = service.registry.list_workflows() if args.name == "--all" else [args.name]
    results = []
    for name in names:
        try:
            service.registry.resolve(name)
            ready, detail = service.workflow_status(name)
            results.append({"name": name, "ok": ready, **detail})
        except FileNotFoundError as exc:
            results.append({"name": name, "ok": False, "error": str(exc)})
    all_ok = all(r.get("ok") for r in results)
    emit({"ok": all_ok, "results": results})
    return 0 if all_ok else 1


def cmd_workflow_add(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        dest = service.registry.add(Path(args.file), name=args.name, category=args.category)
        emit({"ok": True, "name": dest.stem, "path": str(dest)})
        return 0
    except (FileNotFoundError, ValueError) as exc:
        return emit_error(str(exc))


def cmd_run(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        overrides = _parse_params(args.param)
        if args.prompt:
            overrides.setdefault("positive_prompt", args.prompt)
        result = service.run_workflow(
            args.workflow,
            overrides or None,
            _output_dir(args, service),
            profile_name=args.profile,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("执行失败 workflow={}", args.workflow)
        return emit_error(str(exc))


def cmd_image_t2i(args: argparse.Namespace) -> int:
    if not args.prompt:
        return emit_error("请提供 --prompt/-p")
    service = _service(args)
    try:
        overrides = _parse_params(args.param)
        result = service.t2i(
            args.prompt,
            output_dir=_output_dir(args, service),
            negative_prompt=args.negative,
            workflow_name=args.workflow,
            profile_name=args.profile,
            **overrides,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("t2i 失败")
        return emit_error(str(exc))


def cmd_image_i2i(args: argparse.Namespace) -> int:
    service = _service(args)
    workflow = args.workflow or service.resolve_workflow_for_capability("image", "i2i")
    if not workflow:
        return emit_error("未配置 image.i2i 工作流，请使用 comfyui config set capabilities.image.i2i <name>")
    if not args.input:
        return emit_error("请提供 --input 参考图")
    if not args.prompt:
        return emit_error("请提供 --prompt/-p")
    try:
        uploaded = service.api.upload_image(args.input)
        overrides = _parse_params(args.param)
        overrides["image_name"] = uploaded
        overrides["positive_prompt"] = args.prompt
        if args.negative:
            overrides["negative_prompt"] = args.negative
        result = service.run_workflow(
            workflow,
            overrides,
            _output_dir(args, service),
            profile_name=args.profile,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_error(str(exc))


def cmd_video_t2v(args: argparse.Namespace) -> int:
    if not args.prompt:
        return emit_error("请提供 --prompt/-p")
    service = _service(args)
    try:
        overrides = _parse_params(args.param)
        if args.length:
            overrides["length"] = args.length
        result = service.t2v(
            args.prompt,
            output_dir=_output_dir(args, service),
            negative_prompt=args.negative,
            workflow_name=args.workflow,
            profile_name=args.profile,
            **overrides,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_error(str(exc))


def cmd_video_i2v(args: argparse.Namespace) -> int:
    if not args.input:
        return emit_error("请提供 --input 关键帧图片")
    if not args.prompt:
        return emit_error("请提供 --prompt/-p 运动描述")
    service = _service(args)
    try:
        overrides = _parse_params(args.param)
        result = service.i2v(
            args.input,
            args.prompt,
            output_dir=_output_dir(args, service),
            negative_prompt=args.negative,
            duration_sec=args.duration,
            workflow_name=args.workflow,
            profile_name=args.profile,
            length=args.length,
            **overrides,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_error(str(exc))


def cmd_digital_run(args: argparse.Namespace) -> int:
    if not args.portrait:
        return emit_error("请提供 --portrait 人物图")
    if not args.audio:
        return emit_error("请提供 --audio 音频文件")
    service = _service(args)
    try:
        result = run_lip_sync(
            service,
            Path(args.portrait),
            Path(args.audio),
            _output_dir(args, service),
            workflow_name=args.workflow,
        )
        emit(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_error(str(exc))


def cmd_digital_pipeline(args: argparse.Namespace) -> int:
    if not args.portrait:
        return emit_error("请提供 --portrait 人物图")
    service = _service(args)
    try:
        result = run_pipeline(
            service,
            portrait=Path(args.portrait),
            script=args.script or "",
            product=Path(args.product) if args.product else None,
            audio=Path(args.audio) if args.audio else None,
            output_dir=_output_dir(args, service),
        )
        emit(result)
        return 0 if result.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        return emit_error(str(exc))


def _mask_secrets(data: dict[str, Any]) -> dict[str, Any]:
    masked = dict(data)
    providers = masked.get("providers", {})
    rh = providers.get("runninghub", {})
    if rh.get("api_key"):
        rh = dict(rh)
        rh["api_key"] = "***"
        providers = dict(providers)
        providers["runninghub"] = rh
        masked["providers"] = providers
    return masked


def cmd_config_show(args: argparse.Namespace) -> int:
    manager = ConfigManager(root=getattr(args, "root", None))
    config = manager.load()
    emit({"ok": True, "config_path": str(manager.config_path), "config": _mask_secrets(config.model_dump())})
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    manager = ConfigManager(root=getattr(args, "root", None))
    keys = args.key.split(".")
    patch: dict[str, Any] = {}
    cursor = patch
    for key in keys[:-1]:
        cursor[key] = {}
        cursor = cursor[key]

    raw = args.value
    if raw.lower() in ("true", "false"):
        value: Any = raw.lower() == "true"
    elif raw == "null":
        value = None
    else:
        try:
            value = int(raw) if "." not in raw else float(raw)
        except ValueError:
            value = raw
    cursor[keys[-1]] = value

    config = manager.update(patch)
    if args.save:
        manager.save(config)
    emit({"ok": True, "updated": args.key, "value": value, "saved": args.save})
    return 0


def cmd_config_validate(args: argparse.Namespace) -> int:
    service = _service(args)
    manager = ConfigManager(root=service.root)
    config = manager.load(reload=True)
    workflows = service.registry.list_workflows()
    emit(
        {
            "ok": True,
            "root": str(service.root),
            "config_path": str(manager.config_path),
            "workflows": workflows,
            "default_profile": config.comfyui.default_profile,
            "capabilities": config.capabilities.model_dump(),
        }
    )
    return 0


def _add_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="Comfyui-CLI 项目根目录（默认自动发现）")


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output", help="输出目录")


def _add_profile_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="配置 profile 名称（默认 fast）")


def _add_param_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p",
        "--param",
        action="append",
        default=[],
        help="覆盖 inject 参数，格式 key=value，可重复",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comfyui",
        description="Comfyui-CLI — 图片/视频/数字人 ComfyUI 能力封装",
    )
    parser.add_argument("--version", action="version", version=f"comfyui {__version__}")

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="日志级别")
    _add_root_arg(parent)

    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", parents=[parent], help="初始化 ~/.comfyui 配置")
    init.add_argument("--project-root", help="绑定项目根目录")
    init.add_argument("--cwd", action="store_true", help="自动检测当前目录为 root")
    init.add_argument("--force", action="store_true", help="覆盖已有配置")
    init.set_defaults(handler=cmd_init)

    health = sub.add_parser("health", parents=[parent], help="健康检查（含工作流就绪）")
    health.set_defaults(handler=cmd_health)

    status = sub.add_parser("status", parents=[parent], help="ComfyUI 连通性")
    status.add_argument("--endpoint")
    status.set_defaults(handler=cmd_status)

    workflow = sub.add_parser("workflow", parents=[parent], help="工作流管理")
    wf_sub = workflow.add_subparsers(dest="workflow_action", required=True)

    wf_list = wf_sub.add_parser("list", help="列出工作流")
    wf_list.add_argument("--category", choices=["image", "video", "digital", "custom"])
    wf_list.set_defaults(handler=cmd_workflow_list)

    wf_inspect = wf_sub.add_parser("inspect", help="查看 inject 字段与 defaults")
    wf_inspect.add_argument("name")
    wf_inspect.set_defaults(handler=cmd_workflow_inspect)

    wf_validate = wf_sub.add_parser("validate", help="校验工作流")
    wf_validate.add_argument("name", help="工作流名或 --all")
    wf_validate.set_defaults(handler=cmd_workflow_validate)

    wf_add = wf_sub.add_parser("add", help="注册自定义工作流到 data/workflows/")
    wf_add.add_argument("file", help="工作流 JSON 路径")
    wf_add.add_argument("--name", help="注册名称（默认取文件名）")
    wf_add.add_argument("--category", default="custom")
    wf_add.set_defaults(handler=cmd_workflow_add)

    run = sub.add_parser("run", parents=[parent], help="按工作流名执行")
    run.add_argument("workflow", help="工作流名称")
    run.add_argument("--prompt", help="positive_prompt 简写")
    _add_param_arg(run)
    _add_profile_arg(run)
    _add_output_arg(run)
    run.set_defaults(handler=cmd_run)

    image = sub.add_parser("image", parents=[parent], help="图片生成")
    img_sub = image.add_subparsers(dest="image_action", required=True)

    t2i = img_sub.add_parser("t2i", help="文生图")
    t2i.add_argument("--prompt", "-t", help="正向提示词")
    t2i.add_argument("--negative", help="负向提示词")
    t2i.add_argument("--workflow", help="覆盖默认工作流")
    _add_param_arg(t2i)
    _add_profile_arg(t2i)
    _add_output_arg(t2i)
    t2i.set_defaults(handler=cmd_image_t2i)

    i2i = img_sub.add_parser("i2i", help="图生图")
    i2i.add_argument("--input", required=True, help="参考图路径")
    i2i.add_argument("--prompt", "-t", help="正向提示词")
    i2i.add_argument("--negative")
    i2i.add_argument("--workflow")
    _add_param_arg(i2i)
    _add_profile_arg(i2i)
    _add_output_arg(i2i)
    i2i.set_defaults(handler=cmd_image_i2i)

    video = sub.add_parser("video", parents=[parent], help="视频生成")
    vid_sub = video.add_subparsers(dest="video_action", required=True)

    t2v = vid_sub.add_parser("t2v", help="文生视频")
    t2v.add_argument("--prompt", "-t")
    t2v.add_argument("--negative")
    t2v.add_argument("--workflow")
    t2v.add_argument("--length", type=int)
    _add_param_arg(t2v)
    _add_profile_arg(t2v)
    _add_output_arg(t2v)
    t2v.set_defaults(handler=cmd_video_t2v)

    i2v = vid_sub.add_parser("i2v", help="图生视频")
    i2v.add_argument("--input", required=True)
    i2v.add_argument("--prompt", "-t")
    i2v.add_argument("--negative")
    i2v.add_argument("--workflow")
    i2v.add_argument("--duration", type=float, help="目标时长（秒）")
    i2v.add_argument("--length", type=int, help="直接指定帧数")
    _add_param_arg(i2v)
    _add_profile_arg(i2v)
    _add_output_arg(i2v)
    i2v.set_defaults(handler=cmd_video_i2v)

    digital = sub.add_parser("digital", parents=[parent], help="数字人")
    dig_sub = digital.add_subparsers(dest="digital_action", required=True)

    dig_run = dig_sub.add_parser("run", help="图+音频口播合成")
    dig_run.add_argument("--portrait", required=True)
    dig_run.add_argument("--audio", required=True)
    dig_run.add_argument("--workflow")
    _add_output_arg(dig_run)
    dig_run.set_defaults(handler=cmd_digital_run)

    dig_pipe = dig_sub.add_parser("pipeline", help="带货多步链")
    dig_pipe.add_argument("--portrait", required=True)
    dig_pipe.add_argument("--product")
    dig_pipe.add_argument("--script")
    dig_pipe.add_argument("--audio")
    _add_output_arg(dig_pipe)
    dig_pipe.set_defaults(handler=cmd_digital_pipeline)

    config = sub.add_parser("config", parents=[parent], help="配置管理")
    cfg_sub = config.add_subparsers(dest="config_action", required=True)

    cfg_show = cfg_sub.add_parser("show", help="查看配置")
    cfg_show.set_defaults(handler=cmd_config_show)

    cfg_set = cfg_sub.add_parser("set", help="设置配置项")
    cfg_set.add_argument("key", help="点分路径，如 capabilities.video.t2v")
    cfg_set.add_argument("value")
    cfg_set.add_argument("--save", action="store_true", help="写入配置文件")
    cfg_set.set_defaults(handler=cmd_config_set)

    cfg_validate = cfg_sub.add_parser("validate", help="校验配置与工作流")
    cfg_validate.set_defaults(handler=cmd_config_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv or sys.argv[1:])
    _configure_logging(args.log_level)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
