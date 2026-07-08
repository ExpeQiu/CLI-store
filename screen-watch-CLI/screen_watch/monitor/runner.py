"""监控主循环"""

from __future__ import annotations

import json
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, TextIO

from screen_watch.capture import find_window, is_window_frontmost, require_capture_deps
from screen_watch.config import AppConfig
from screen_watch.monitor.pipeline import RegionPipeline
from screen_watch.ocr.factory import OcrBackend, require_ocr_deps
from screen_watch.storage.sqlite_store import SqliteStore
from screen_watch.utils.demo import demo_monitor_events
from screen_watch.utils.errors import EXIT_PERMISSION, EXIT_SCRAPE_FAIL
from screen_watch.utils.logger import setup_logger

TZ_CN = timezone(timedelta(hours=8))
logger = setup_logger()


def _now_iso() -> str:
    return datetime.now(TZ_CN).isoformat()


def _emit_event(output: TextIO, event: dict[str, Any], fmt: str) -> None:
    if fmt == "jsonl":
        output.write(json.dumps(event, ensure_ascii=False) + "\n")
        output.flush()
    elif fmt == "table":
        if event.get("type") == "metric":
            output.write(f"[metric] {event.get('viewer_count')} {event.get('raw', '')}\n")
        elif event.get("type") == "chat":
            user = event.get("user") or "?"
            output.write(f"[chat] {user}: {event.get('content', '')}\n")
        output.flush()


def run_monitor_demo(
    *,
    config: AppConfig,
    fmt: str,
    output: TextIO,
) -> None:
    events = demo_monitor_events()
    if fmt == "jsonl":
        for ev in events:
            _emit_event(output, ev, fmt)
    elif fmt == "table":
        for ev in events:
            _emit_event(output, ev, fmt)
    else:
        payload = {
            "module": "monitor-run",
            "data_source": "demo",
            "preset": config.preset,
            "fetched_at": _now_iso(),
            "count": len(events),
            "events": events,
        }
        output.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    logger.info("demo 模式输出 %d 条事件", len(events))


def run_monitor_live(
    *,
    config: AppConfig,
    fmt: str,
    output: TextIO,
    interval: float | None = None,
    save_db: str | None = None,
    regions: list[str] | None = None,
    require_foreground: bool = False,
    ocr_backend: OcrBackend = "auto",
) -> None:
    require_capture_deps()
    require_ocr_deps()

    tick = interval or config.interval_sec
    watch_regions = regions or ["viewer_count", "chat"]
    pipeline = RegionPipeline(config, ocr_backend=ocr_backend)
    store: SqliteStore | None = None
    session_id: int | None = None
    running = True

    def _stop(*_args: Any) -> None:
        nonlocal running
        running = False
        logger.info("收到停止信号，准备退出…")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    if save_db:
        store = SqliteStore(save_db)
        session_id = store.start_session(config.preset, config.window_title)

    logger.info(
        "启动 OCR 监控 preset=%s window=%s interval=%.1fs regions=%s",
        config.preset,
        config.window_title,
        tick,
        watch_regions,
    )

    miss_count = 0
    while running:
        try:
            window = find_window(config.window_title)
            if window is None:
                miss_count += 1
                logger.warning(
                    "未找到窗口 title~=%r（连续 %d 次）",
                    config.window_title,
                    miss_count,
                )
                if miss_count >= 20:
                    raise RuntimeError(f"连续未找到窗口: {config.window_title}")
                time.sleep(tick)
                continue

            miss_count = 0
            if require_foreground and not is_window_frontmost(window):
                logger.debug("窗口非前台，跳过本轮: %s", window.label)
                time.sleep(tick)
                continue

            logger.debug("绑定窗口 %s bounds=%s", window.label, window.bounds)

            if "viewer_count" in watch_regions:
                metric = pipeline.process_viewer(window)
                if metric:
                    _emit_event(output, metric, fmt)
                    if store and session_id is not None:
                        store.save_event(session_id, metric)
                    logger.info("metric viewer_count=%s", metric.get("viewer_count"))

            if "chat" in watch_regions:
                chats = pipeline.process_chat(window)
                for chat in chats:
                    _emit_event(output, chat, fmt)
                    if store and session_id is not None:
                        store.save_event(session_id, chat)

        except PermissionError as exc:
            logger.error("%s", exc)
            if store and session_id is not None:
                store.end_session(session_id)
                store.close()
            raise SystemExit(EXIT_PERMISSION) from exc
        except Exception as exc:
            logger.exception("监控循环异常: %s", exc)
            if store and session_id is not None:
                store.end_session(session_id)
                store.close()
            raise SystemExit(EXIT_SCRAPE_FAIL) from exc

        time.sleep(tick)

    if store and session_id is not None:
        store.end_session(session_id)
        store.close()
    logger.info("监控已停止")


def run_monitor(
    *,
    config: AppConfig,
    demo: bool,
    fmt: str = "jsonl",
    output: TextIO | None = None,
    interval: float | None = None,
    save_db: str | None = None,
    regions: list[str] | None = None,
    require_foreground: bool = False,
    ocr_backend: OcrBackend = "auto",
) -> None:
    out = output or sys.stdout

    if demo:
        run_monitor_demo(config=config, fmt=fmt, output=out)
        return

    run_monitor_live(
        config=config,
        fmt=fmt,
        output=out,
        interval=interval,
        save_db=save_db,
        regions=regions,
        require_foreground=require_foreground,
        ocr_backend=ocr_backend,
    )
