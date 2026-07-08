"""screen-watch CLI 入口"""

from __future__ import annotations

import json
import logging
import sys

import click

from screen_watch.__version__ import __version__
from screen_watch.calibrate import run_calibrate
from screen_watch.capture import find_window, list_windows, require_capture_deps
from screen_watch.config import load_config, wechat_live_default
from screen_watch.monitor.pipeline import RegionPipeline
from screen_watch.monitor.runner import run_monitor
from screen_watch.ocr.factory import require_ocr_deps
from screen_watch.utils.demo import demo_monitor_payload
from screen_watch.utils.errors import EXIT_ERROR, EXIT_NO_DATA, EXIT_OK, EXIT_PERMISSION, EXIT_SCRAPE_FAIL
from screen_watch.utils.logger import setup_logger

logger = setup_logger()


def _version_callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"screen-watch {__version__}")
    ctx.exit(EXIT_OK)


def _resolve_config(config_path: str | None, preset: str, window_title: str | None) -> "AppConfig":
    from screen_watch.config import AppConfig

    if config_path:
        config = load_config(config_path)
    else:
        loaded = load_config()
        config = loaded if loaded.regions else wechat_live_default()
    config.preset = preset
    if window_title:
        config.window_title = window_title
    return config


@click.group()
@click.option("--version", is_flag=True, callback=_version_callback, expose_value=False, is_eager=True)
@click.option("-v", "--verbose", is_flag=True, help="DEBUG 日志")
@click.option("-q", "--quiet", is_flag=True, help="仅 WARNING 及以上")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """屏幕区域 OCR 直播监控 — 主攻微信客户端直播"""
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    ctx.ensure_object(dict)


@cli.group()
def monitor() -> None:
    """监控子命令"""


@monitor.command("run")
@click.option("--preset", default="wechat-live", help="预设配置")
@click.option("--window", "window_title", default=None, help="窗口标题匹配")
@click.option("--config", "config_path", type=click.Path(), default=None, help="配置文件路径")
@click.option("--interval", type=float, default=None, help="截屏间隔（秒）")
@click.option(
    "--region",
    "regions",
    multiple=True,
    type=click.Choice(["viewer_count", "chat"]),
    help="监控区域，可多次指定；默认两者都监控",
)
@click.option("--format", "fmt", type=click.Choice(["json", "jsonl", "table"]), default="jsonl")
@click.option("-o", "--output", type=click.File("w"), default=None, help="输出文件，默认 stdout")
@click.option("--save", "save_db", default=None, help="SQLite 落库路径，如 logs/screen-watch.db")
@click.option("--require-foreground", is_flag=True, help="仅在前台窗口时 OCR（避免遮挡误识别）")
@click.option(
    "--ocr-engine",
    type=click.Choice(["auto", "paddle", "vision"]),
    default="auto",
    help="OCR 引擎：auto 优先 Paddle，不可用时 macOS Vision",
)
@click.option("--demo", is_flag=True, help="Mock OCR 结果，不截屏")
def monitor_run(
    preset: str,
    window_title: str | None,
    config_path: str | None,
    interval: float | None,
    regions: tuple[str, ...],
    fmt: str,
    output,
    save_db: str | None,
    require_foreground: bool,
    ocr_engine: str,
    demo: bool,
) -> None:
    """启动 OCR 监控循环"""
    config = _resolve_config(config_path, preset, window_title)
    region_list = list(regions) if regions else None

    try:
        run_monitor(
            config=config,
            demo=demo,
            fmt=fmt,
            output=output,
            interval=interval,
            save_db=save_db,
            regions=region_list,
            require_foreground=require_foreground,
            ocr_backend=ocr_engine,  # type: ignore[arg-type]
        )
    except SystemExit:
        raise
    except PermissionError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_PERMISSION) from exc
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_SCRAPE_FAIL) from exc


@cli.command("ocr")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="图片路径")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option(
    "--ocr-engine",
    type=click.Choice(["auto", "paddle", "vision"]),
    default="auto",
)
def ocr_image(input_path: str, fmt: str, ocr_engine: str) -> None:
    """对本地图片 OCR（无需截屏）"""
    try:
        require_ocr_deps()
        import cv2
        from screen_watch.ocr.factory import get_ocr_engine
        from screen_watch.parsers.wechat_live import ocr_lines_to_text

        image = cv2.imread(input_path)
        if image is None:
            click.echo(f"无法读取图片: {input_path}", err=True)
            raise SystemExit(EXIT_ERROR)

        engine = get_ocr_engine(ocr_engine)  # type: ignore[arg-type]
        lines = engine.recognize(image)
        text = ocr_lines_to_text(lines)
        if fmt == "text":
            click.echo(text)
            return
        click.echo(
            json.dumps(
                {
                    "module": "ocr",
                    "input": input_path,
                    "engine": getattr(engine, "name", "unknown"),
                    "text": text,
                    "lines": lines,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_ERROR) from exc


@cli.group()
def capture() -> None:
    """截屏调试"""


@capture.command("once")
@click.option("--region", required=True, help="区域名: viewer_count | chat | full")
@click.option("--window", "window_title", default="微信")
@click.option("--config", "config_path", type=click.Path(), default=None)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option(
    "--ocr-engine",
    type=click.Choice(["auto", "paddle", "vision"]),
    default="auto",
)
@click.option("--save-crop", default=None, help="保存 OCR 裁剪图路径，便于校准")
@click.option("--demo", is_flag=True, help="输出 demo OCR 文本")
def capture_once(
    region: str,
    window_title: str,
    config_path: str | None,
    fmt: str,
    ocr_engine: str,
    save_crop: str | None,
    demo: bool,
) -> None:
    """单帧截屏 + OCR 调试"""
    if demo:
        click.echo(json.dumps(demo_monitor_payload(), ensure_ascii=False, indent=2))
        return

    try:
        require_capture_deps()
        require_ocr_deps()
        config = _resolve_config(config_path, "wechat-live", window_title)
        window = find_window(config.window_title)
        if window is None:
            click.echo(f"未找到窗口: {config.window_title}", err=True)
            raise SystemExit(EXIT_SCRAPE_FAIL)

        pipeline = RegionPipeline(config, ocr_backend=ocr_engine)  # type: ignore[arg-type]
        result = pipeline.capture_region_once(window, region, save_crop=save_crop)
        if fmt == "text":
            click.echo(result.get("text", ""))
        else:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except PermissionError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_PERMISSION) from exc
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_ERROR) from exc


@cli.group()
def window() -> None:
    """窗口管理"""


@window.command("list")
@click.option("--filter", "title_filter", default="", help="标题过滤")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def window_list(title_filter: str, fmt: str) -> None:
    """列出可绑定窗口"""
    try:
        require_capture_deps()
        windows = list_windows(title_filter)
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_ERROR) from exc
    except PermissionError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_PERMISSION) from exc

    if fmt == "json":
        payload = {
            "module": "window-list",
            "data_source": "live",
            "count": len(windows),
            "items": [
                {
                    "title": w.title,
                    "owner": w.owner,
                    "label": w.label,
                    "bounds": w.bounds,
                    "window_id": w.window_id,
                }
                for w in windows
            ],
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not windows:
        click.echo("无匹配窗口", err=True)
        raise SystemExit(EXIT_NO_DATA)

    for w in windows:
        click.echo(f"{w.label}\t{w.bounds}")


@cli.command("pick")
@click.option("--window", "window_title", default="微信")
@click.option("--window-index", type=int, default=None)
@click.option("--save-config", "save_config_path", default="config.yaml")
@click.pass_context
def pick_regions_cmd(ctx, window_title: str, window_index: int | None, save_config_path: str) -> None:
    """打开框选窗口（calibrate 快捷方式）"""
    ctx.invoke(
        calibrate,
        preset="wechat-live",
        window_title=window_title,
        save_config_path=save_config_path,
        use_defaults=False,
        pick=True,
        pick_mode="screenshot",
        window_index=window_index,
        regions=(),
    )


@cli.command("calibrate")
@click.option("--preset", default="wechat-live")
@click.option("--window", "window_title", default="微信")
@click.option("--save-config", "save_config_path", default=None, help="写入 config.yaml 路径")
@click.option("--defaults", "use_defaults", is_flag=True, help="跳过框选，使用内置默认区域")
@click.option(
    "--pick/--no-pick",
    default=True,
    help="悬浮框选标记识别区域（默认开启）",
)
@click.option(
    "--pick-mode",
    type=click.Choice(["overlay", "screenshot"]),
    default="screenshot",
    help="screenshot=截图弹窗框选（推荐）；overlay=同 screenshot",
)
@click.option("--window-index", type=int, default=None, help="多窗口时指定序号，见 window list")
@click.option(
    "--region",
    "regions",
    multiple=True,
    type=click.Choice(["viewer_count", "chat"]),
    help="要框选的区域，默认两个都选",
)
def calibrate(
    preset: str,
    window_title: str,
    save_config_path: str | None,
    use_defaults: bool,
    pick: bool,
    pick_mode: str,
    window_index: int | None,
    regions: tuple[str, ...],
) -> None:
    """截图弹窗框选 — 标记 OCR 识别区域"""
    try:
        require_capture_deps()
        region_list = list(regions) if regions else None
        run_calibrate(
            preset=preset,
            window_title=window_title,
            save_config_path=save_config_path or "config.yaml",
            use_defaults=use_defaults,
            use_pick=pick and not use_defaults,
            pick_mode=pick_mode,
            region_names=region_list,
            window_index=window_index,
        )
    except PermissionError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_PERMISSION) from exc
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(EXIT_SCRAPE_FAIL) from exc


def main() -> int:
    try:
        cli(obj={})
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return EXIT_OK
        if isinstance(code, int):
            return code
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
