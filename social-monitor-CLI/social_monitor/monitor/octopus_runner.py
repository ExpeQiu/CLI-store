"""Octopus CLI 调用与结果入库"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from social_monitor.importers.octopus import import_octopus_file
from social_monitor.monitor.routes import (
    BACKEND_OCTOPUS,
    build_octopus_cli_args,
    get_octopus_cli,
    resolve_octopus_template,
    resolve_route,
)
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class OctopusRunError(RuntimeError):
    """Octopus CLI 执行失败"""


def run_octopus_collect(
    route_key: str,
    monitor_cfg: Dict[str, Any],
    output_file: Path,
    ctx: Dict[str, Any],
    timeout: int = 3600,
) -> Path:
    """调用 Octopus CLI 采集并返回输出文件路径"""
    resolved = resolve_route(route_key, monitor_cfg)
    template = resolved.get("octopus_template")
    if not template:
        raise OctopusRunError(f"路由 {route_key} 未配置 Octopus 模板")

    cli = get_octopus_cli(monitor_cfg)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd: List[str] = [
        cli,
        "run",
        template,
        *build_octopus_cli_args(route_key, ctx),
        "--output",
        str(output_file),
    ]
    logger.info("Octopus 采集 route=%s cmd=%s", route_key, " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.stdout:
            logger.debug("Octopus stdout: %s", result.stdout[:500])
    except FileNotFoundError:
        raise OctopusRunError(f"未找到 Octopus CLI: {cli}")
    except subprocess.CalledProcessError as e:
        raise OctopusRunError(e.stderr or str(e))
    except subprocess.TimeoutExpired:
        raise OctopusRunError("Octopus 执行超时")

    if not output_file.exists():
        raise OctopusRunError(f"Octopus 未生成输出文件: {output_file}")
    return output_file


def import_octopus_route(
    route_key: str,
    monitor_cfg: Dict[str, Any],
    output_file: Path,
    account_id: str,
    storage=None,
    mode: str = "append",
) -> int:
    resolved = resolve_route(route_key, monitor_cfg)
    platform = resolved["platform"]
    content_type = resolved["content_type"]

    count = import_octopus_file(
        output_file,
        platform=platform,
        content_type=content_type,
        account_id=account_id,
        storage=storage,
        mode=mode,
    )
    if storage and count:
        # import_octopus_file 内部 save mode 固定 append；replace 场景由调用方处理
        logger.info(
            "Octopus 路由入库 route=%s account=%s count=%d mode=%s",
            route_key,
            account_id,
            count,
            mode,
        )
    return count


def route_detail_for_log(route_key: str, monitor_cfg: Dict[str, Any]) -> str:
    resolved = resolve_route(route_key, monitor_cfg)
    backend = resolved["backend"]
    if backend == BACKEND_OCTOPUS:
        tpl = resolved.get("octopus_template") or "?"
        return f"route=octopus template={tpl}"
    return "route=social_monitor"
