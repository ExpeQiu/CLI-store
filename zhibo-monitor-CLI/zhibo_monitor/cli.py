"""zhibo-monitor CLI 入口"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

import typer

# 确保项目根在 path（开发模式 / 未安装时）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.auth_login import PLATFORM_CONFIG, run_platform_login
from app.core.database import Base, engine
from app.ingest.screen_watch import IngestConfig, run_ingest
from app.scraper.bilibili import BilibiliScraper
from app.scraper.douyin import DouyinScraper
from app.scraper.sph import SphScraper
from app.scraper.weibo import WeiboScraper
from scripts.backfill_danmaku_analysis import main as backfill_danmaku_analysis_main
from zhibo_monitor.__version__ import __version__
from zhibo_monitor.utils.errors import EXIT_ERROR, EXIT_OK
from zhibo_monitor.utils.logger import setup_logger

logger = setup_logger()

app = typer.Typer(
    help="新能源车企发布会直播监控与分析中台 CLI",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"zhibo-monitor {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="显示版本",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="DEBUG 日志"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="仅 WARNING 及以上"),
) -> None:
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


@app.command("init-db")
def init_db() -> None:
    """初始化数据库表结构"""
    logger.info("初始化数据库表结构")
    Base.metadata.create_all(bind=engine)
    typer.echo("数据库表结构初始化成功", err=True)


@app.command("login")
def login(platform: str) -> None:
    """保存指定平台的登录状态（弹窗扫码）。"""
    platform_name = platform.lower()
    if platform_name not in PLATFORM_CONFIG:
        supported = ", ".join(PLATFORM_CONFIG)
        typer.echo(f"平台 {platform} 暂不支持 login，当前支持: {supported}", err=True)
        raise typer.Exit(code=EXIT_ERROR)

    auth_dir = os.path.join(os.getcwd(), "auth")
    os.makedirs(auth_dir, exist_ok=True)
    auth_file = os.path.join(auth_dir, f"{platform_name}_state.json")

    try:
        asyncio.run(run_platform_login(platform_name, auth_file))
    except KeyboardInterrupt:
        typer.echo("\n登录过程被手动终止", err=True)


@app.command("analyze")
def analyze(
    task_id: Optional[int] = typer.Option(None, "--task-id", help="指定需要回填分析的任务 ID"),
    event_id: str = typer.Option("", "--event-id", help="SIM 场次 ID，仅分析该场次关联任务"),
    all_tasks: bool = typer.Option(False, "--all", help="回填全部任务的弹幕分析"),
    force: bool = typer.Option(False, "--force", help="覆盖已有分析结果"),
) -> None:
    """回填弹幕情感、意向与关键词分析结果"""
    if not all_tasks and task_id is None and not event_id:
        typer.echo(
            "请通过 --task-id、--event-id 指定范围，或使用 --all 处理全部任务。",
            err=True,
        )
        raise typer.Exit(code=EXIT_ERROR)

    argv = ["backfill_danmaku_analysis.py"]
    if task_id is not None:
        argv.extend(["--task-id", str(task_id)])
    if event_id:
        argv.extend(["--event-id", event_id])
    if all_tasks:
        argv.append("--all")
    if force:
        argv.append("--force")

    original_argv = sys.argv[:]
    try:
        sys.argv = argv
        exit_code = backfill_danmaku_analysis_main()
    finally:
        sys.argv = original_argv

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command("ingest")
def ingest(
    platform: str = typer.Option("sph-client", "--platform", help="平台标识，默认 sph-client"),
    room_id: str = typer.Option("wechat-ocr", "--room-id", help="房间/来源标识"),
    event_name: str = typer.Option("微信客户端直播-OCR", "--event-name", help="发布会名称"),
    car_brand: str = typer.Option("unknown", "--car-brand", help="车企品牌"),
    car_model: str = typer.Option("", "--car-model", help="车型"),
    event_id: str = typer.Option("", "--event-id", help="SIM 场次 ID"),
    task_id: Optional[int] = typer.Option(None, "--task-id", help="复用已有任务 ID"),
    stdin: bool = typer.Option(True, "--stdin/--no-stdin", help="从 stdin 读取 JSONL"),
    finish_on_eof: bool = typer.Option(True, "--finish-on-eof/--keep-running", help="stdin 结束后标记任务停止"),
    demo: bool = typer.Option(False, "--demo", help="使用内置示例 JSONL，不读 stdin"),
) -> None:
    """接收 screen-watch JSONL 管道并写入数据库"""
    import json

    if not stdin and not demo:
        typer.echo("请启用 --stdin 或使用 --demo", err=True)
        raise typer.Exit(code=EXIT_ERROR)

    cfg = IngestConfig(
        platform=platform.lower(),
        room_id=room_id,
        event_name=event_name,
        car_brand=car_brand,
        car_model=car_model,
        event_id=event_id or None,
        task_id=task_id,
        finish_on_eof=finish_on_eof,
    )

    source = sys.stdin if stdin and not demo else sys.stdin
    if demo:
        import io
        source = io.StringIO("")

    logger.info(
        "ingest platform=%s room_id=%s demo=%s task_id=%s",
        cfg.platform,
        cfg.room_id,
        demo,
        cfg.task_id,
    )

    try:
        result = run_ingest(source, cfg, demo=demo)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_ERROR) from exc

    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    typer.echo(
        f"入库完成 task_id={result.get('task_id')} "
        f"metrics={result.get('metrics')} chats={result.get('chats')}",
        err=True,
    )


@app.command("start")
def start_monitor(
    platform: str,
    room_id: str,
    event_name: str = typer.Option("未命名发布会", "--event-name", help="发布会名称"),
    car_brand: str = typer.Option("unknown", "--car-brand", help="车企品牌"),
    car_model: str = typer.Option("", "--car-model", help="车型"),
    event_id: str = typer.Option("", "--event-id", help="SIM 场次 ID（关联 event_metadata）"),
    headless: bool = typer.Option(True, "--headless/--headed", help="是否使用无头浏览器"),
    demo: bool = typer.Option(False, "--demo", help="演示模式：仅打印配置摘要不启动浏览器"),
) -> None:
    """启动指定平台的直播间监控"""
    platform_name = platform.lower()
    if demo:
        payload = {
            "module": "monitor-start",
            "data_source": "demo",
            "platform": platform_name,
            "room_id": room_id,
            "event_name": event_name,
            "car_brand": car_brand,
            "car_model": car_model,
            "event_id": event_id,
        }
        import json
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    Base.metadata.create_all(bind=engine)

    if platform_name == "bilibili":
        scraper = BilibiliScraper(
            room_id=room_id,
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id or None,
            headless=headless,
        )
    elif platform_name == "douyin":
        scraper = DouyinScraper(
            room_id=room_id,
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id or None,
            headless=headless,
        )
    elif platform_name == "sph":
        scraper = SphScraper(
            room_id=room_id,
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id or None,
            headless=headless,
        )
    elif platform_name == "weibo":
        scraper = WeiboScraper(
            room_id=room_id,
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id or None,
            headless=headless,
        )
    else:
        typer.echo(f"暂不支持平台: {platform}", err=True)
        raise typer.Exit(code=EXIT_ERROR)

    logger.info("启动 %s 监控 room_id=%s event=%s", platform_name, room_id, event_name)
    typer.echo(f"启动 {platform_name} 监控任务，房间号: {room_id}", err=True)
    try:
        asyncio.run(scraper.run_loop())
    except KeyboardInterrupt:
        typer.echo("\n监控任务被手动终止", err=True)
        asyncio.run(scraper.stop())


def main() -> int:
    try:
        app()
    except typer.Exit as exc:
        return int(exc.exit_code or EXIT_OK)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
