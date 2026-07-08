import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import click
import yaml

from social_monitor.__version__ import __version__
from social_monitor.utils.demo import (
    demo_bilibili_ranking,
    demo_douyin_trending,
    demo_weibo_trending,
    demo_zhihu_trending,
)
from social_monitor.utils.errors import EXIT_ERROR, EXIT_NO_DATA, EXIT_OK, EXIT_SCRAPE_FAIL
from social_monitor.config import get_rsshub_url, init_config
from social_monitor.notifiers.feishu import FeishuNotifier
from social_monitor.platforms.bilibili import BilibiliCollector
from social_monitor.platforms.douyin import DouYinCollector
from social_monitor.platforms.wechat import WeChatCollector
from social_monitor.platforms.weibo import WeiboCollector
from social_monitor.platforms.xiaohongshu import XiaoHongShuCollector
from social_monitor.platforms.zhihu import ZhihuCollector
from social_monitor.storage.factory import close_storage, get_storage
from social_monitor.utils.cookie_manager import (
    CONFIG_FILE,
    get_browser_dir,
    get_cookie,
    get_cookie_source,
    has_browser_session,
    load_config,
    save_cookie,
)
from social_monitor.utils.cookie_checker import check_platform
from social_monitor.utils.diff_helper import load_and_diff
from social_monitor.utils.logger import setup_logger
from social_monitor.utils.prefetch import ensure_ready

logger = setup_logger()


_FORMAT_CHOICES = ("json", "csv", "print", "table")


def _is_mock_mode(demo: bool = False) -> bool:
    if demo:
        return True
    return os.getenv("SOCIAL_MONITOR_MOCK_MODE", "").lower() in ("1", "true", "yes")


def _resolve_fmt(fmt: Optional[str], legacy_output: Optional[str]) -> str:
    """--format 优先；--output 为 json|csv|print 时视为格式（兼容旧版）"""
    if fmt:
        return fmt
    if legacy_output in _FORMAT_CHOICES:
        return legacy_output
    return "json"


def _resolve_output_file(legacy_output: Optional[str]) -> Optional[str]:
    if legacy_output and legacy_output not in _FORMAT_CHOICES:
        return legacy_output
    return None


def _render_payload(data: List[Any], fmt: str, module: str, data_source: str) -> str:
    display_fmt = "print" if fmt == "table" else fmt
    if display_fmt == "json":
        payload = {
            "module": module,
            "version": __version__,
            "data_source": data_source,
            "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "count": len(data),
            "items": data,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if display_fmt == "csv":
        if not data:
            return ""
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return buf.getvalue()
    lines = []
    for i, item in enumerate(data, 1):
        lines.append(f"--- [{i}] ---")
        for k, v in item.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _emit_output(
    data: List[Any],
    fmt: str,
    *,
    module: str = "fetch",
    data_source: str = "live",
    output_file: Optional[str] = None,
) -> int:
    """数据 → stdout / 文件；返回 exit code"""
    text = _render_payload(data, fmt, module, data_source)
    if output_file:
        Path(output_file).expanduser().write_text(text, encoding="utf-8")
        click.echo(f"已写入 {output_file}", err=True)
    else:
        click.echo(text)
    if not data and data_source == "live":
        return EXIT_NO_DATA
    return EXIT_OK


def _output(data: List[Any], fmt: str) -> None:
    """统一输出格式（兼容旧调用）"""
    _emit_output(data, fmt)


def _maybe_save(
    data: List[Any], platform: str, account_id: str, save: bool, storage_type: str = None
) -> None:
    if not save or not data:
        return
    storage, label = get_storage(storage_type)
    try:
        total = storage.save(platform, account_id, data)
        click.echo(f"已保存到 {label}，共 {total} 条", err=True)
    finally:
        close_storage(storage)


def _save_with_diff(
    data: List[Any],
    platform: str,
    account_id: str,
    diff: bool,
    save: bool,
    storage_type: str = None,
) -> List[Any]:
    """保存并可选返回增量"""
    if not save:
        return data if not diff else data

    storage, label = get_storage(storage_type)

    try:
        if diff:
            added, merged, prev_count = load_and_diff(storage, platform, account_id, data)
            click.echo(
                f"增量: 历史 {prev_count} 条，本次 {len(data)} 条，新增 {len(added)} 条",
                err=True,
            )
            return added

        total = storage.save(platform, account_id, data)
        click.echo(f"已保存到 {label}，共 {total} 条", err=True)
        return data
    finally:
        close_storage(storage)


@click.group()
@click.version_option(version=__version__, prog_name="social-monitor")
@click.option("-v", "--verbose", is_flag=True, help="详细日志 (DEBUG)")
@click.option("-q", "--quiet", is_flag=True, help="仅 WARNING 及以上")
@click.option("--safe", is_flag=True, help="安全模式：请求间隔 10~20s，适合日常监控")
@click.pass_context
def cli(ctx, verbose: bool, quiet: bool, safe: bool):
    """社交媒体监控 CLI

    支持平台：微博、微信公众号、小红书、抖音、B站、知乎

    示例：
        social-monitor fetch weibo --uid 1974576991
        social-monitor monitor run --task daily
        social-monitor fetch bilibili --uid 614946423
    """
    ctx.ensure_object(dict)
    ctx.obj["safe_mode"] = safe
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)


def _safe_mode(ctx) -> bool:
    if ctx is None:
        return False
    return bool(ctx.obj.get("safe_mode", False))


@cli.group()
@click.option("--skip-check", is_flag=True, help="跳过采集前 Cookie 检测")
@click.pass_context
def fetch(ctx, skip_check):
    """采集指定平台数据"""
    ctx.ensure_object(dict)
    ctx.obj["skip_check"] = skip_check


@fetch.command("weibo")
@click.option("--uid", required=True, help="微博 UID")
@click.option("--pages", default=5, show_default=True, help="抓取页数")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--cookie", help="微博 Cookie（可选）")
@click.option("--save", is_flag=True, help="保存到本地/数据库")
@click.option("--storage", default=None, type=click.Choice(["postgres", "json", "mysql"]))
def fetch_weibo(uid, pages, output, cookie, save, storage):
    """采集微博用户动态"""
    with WeiboCollector(cookie=get_cookie("weibo", cookie)) as collector:
        data = collector.fetch_user_timeline(uid, max_page=pages)
    _output(data, output)
    _maybe_save(data, "weibo", uid, save, storage)


@fetch.command("weibo-trending")
@click.option("--count", default=50, show_default=True, help="热搜条数")
@click.option("--date", default=None, help="快照日期 YYYY-MM-DD，默认今天")
@click.option("--format", "fmt", default=None, type=click.Choice(list(_FORMAT_CHOICES)))
@click.option("--output", "-o", default=None, help="输出文件路径（兼容旧版：json|csv|print 表示格式）")
@click.option("--demo", is_flag=True, help="使用内置示例数据，不访问外网")
@click.option("--save", is_flag=True)
@click.option("--diff", is_flag=True, help="与历史对比，仅输出/通知新增项（需 --save）")
@click.pass_context
def fetch_weibo_trending(ctx, count, date, fmt, output, demo, save, diff):
    """采集微博热搜榜（--save 时按日归档 trending_YYYY-MM-DD）"""
    if diff and not save:
        raise click.ClickException("--diff 需要配合 --save 使用")
    from datetime import date as date_cls

    resolved_fmt = _resolve_fmt(fmt, output)
    output_file = _resolve_output_file(output)
    snapshot_date = date or date_cls.today().isoformat()
    account_id = f"trending_{snapshot_date}"

    if _is_mock_mode(demo):
        data = demo_weibo_trending(count)
        data_source = "demo"
    else:
        try:
            with WeiboCollector(safe_mode=_safe_mode(ctx)) as collector:
                data = collector.fetch_trending(max_count=count)
            data_source = "live"
        except Exception as e:
            logger.error("微博热搜采集失败: %s", e)
            raise SystemExit(EXIT_SCRAPE_FAIL) from e

    for item in data:
        item["snapshot_date"] = snapshot_date
    if diff:
        data = _save_with_diff(data, "weibo", account_id, diff, save)
    elif save:
        storage, label = get_storage()
        try:
            storage.save("weibo", account_id, data, mode="replace")
            click.echo(f"已保存到 {label}，快照 {snapshot_date} 共 {len(data)} 条", err=True)
        finally:
            close_storage(storage)
    raise SystemExit(
        _emit_output(
            data,
            resolved_fmt,
            module="weibo-trending",
            data_source=data_source,
            output_file=output_file,
        )
    )


@fetch.command("wechat")
@click.option("--wxid", required=True, help="微信公众号 ID / biz")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--rsshub-url", default=None, help="RSSHub 地址")
@click.option("--save", is_flag=True)
def fetch_wechat(wxid, output, rsshub_url, save):
    """采集微信公众号文章"""
    url = get_rsshub_url(rsshub_url)
    with WeChatCollector(rsshub_url=url) as collector:
        try:
            data = collector.fetch_via_rsshub(wxid)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
    _output(data, output)
    _maybe_save(data, "wechat", wxid, save)


@fetch.command("xiaohongshu")
@click.option("--user-id", required=True, help="小红书用户 ID")
@click.option("--cookie", default=None, help="小红书 Cookie")
@click.option("--browser/--no-browser", default=None, help="强制使用/禁用 Playwright 浏览器采集")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.option("--diff", is_flag=True)
@click.pass_context
def fetch_xiaohongshu(ctx, user_id, cookie, browser, output, save, diff):
    """采集小红书用户笔记（推荐先 config login xiaohongshu）"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("xiaohongshu", "xiaohongshu", cookie=cookie, skip=skip)
    use_cookie = get_cookie("xiaohongshu", cookie)
    if diff and not save:
        raise click.ClickException("--diff 需要配合 --save 使用")
    with XiaoHongShuCollector(cookie=use_cookie, use_browser=browser) as collector:
        data = collector.fetch_user_notes(user_id)
    data = _save_with_diff(data, "xiaohongshu", user_id, diff, save)
    _output(data, output)


@fetch.command("douyin-trending")
@click.option("--count", default=50, show_default=True, help="热榜条数")
@click.option("--format", "fmt", default=None, type=click.Choice(list(_FORMAT_CHOICES)))
@click.option("--output", "-o", default=None, help="输出文件路径（兼容旧版：json|csv|print 表示格式）")
@click.option("--demo", is_flag=True, help="使用内置示例数据，不访问外网")
@click.option("--save", is_flag=True)
@click.option("--diff", is_flag=True)
@click.pass_context
def fetch_douyin_trending(ctx, count, fmt, output, demo, save, diff):
    """采集抖音热榜"""
    if diff and not save:
        raise click.ClickException("--diff 需要配合 --save 使用")
    resolved_fmt = _resolve_fmt(fmt, output)
    output_file = _resolve_output_file(output)
    if _is_mock_mode(demo):
        data = demo_douyin_trending(count)
        data_source = "demo"
    else:
        try:
            with DouYinCollector() as collector:
                data = collector.fetch_trending(max_count=count)
            data_source = "live"
        except Exception as e:
            logger.error("抖音热榜采集失败: %s", e)
            raise SystemExit(EXIT_SCRAPE_FAIL) from e
    data = _save_with_diff(data, "douyin", "trending", diff, save)
    raise SystemExit(
        _emit_output(
            data,
            resolved_fmt,
            module="douyin-trending",
            data_source=data_source,
            output_file=output_file,
        )
    )


@fetch.command("douyin")
@click.option("--sec-uid", required=True, help="抖音用户 sec_uid")
@click.option("--cookie", default=None, help="抖音 Cookie")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_douyin(ctx, sec_uid, cookie, output, save):
    """采集抖音用户视频"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("douyin-user", "douyin", cookie=cookie, skip=skip)
    use_cookie = get_cookie("douyin", cookie)
    with DouYinCollector(cookie=use_cookie) as collector:
        data = collector.fetch_user_videos(sec_uid, cookie=use_cookie)
    _output(data, output)
    _maybe_save(data, "douyin", sec_uid, save)


@fetch.command("bilibili")
@click.option("--uid", default=None, type=int, help="B站 UP 主 UID")
@click.option("--format", "fmt", default=None, type=click.Choice(list(_FORMAT_CHOICES)))
@click.option("--output", "-o", default=None, help="输出文件路径（兼容旧版：json|csv|print 表示格式）")
@click.option(
    "--type",
    "fetch_type",
    default="video",
    type=click.Choice(["video", "ranking"]),
    help="采集类型",
)
@click.option("--rid", default=0, help="排行榜分区 ID（ranking 模式）")
@click.option("--demo", is_flag=True, help="ranking 模式使用内置示例数据")
@click.option("--save", is_flag=True)
def fetch_bilibili(uid, fmt, output, fetch_type, rid, demo, save):
    """采集B站 UP 主视频或排行榜"""
    resolved_fmt = _resolve_fmt(fmt, output)
    output_file = _resolve_output_file(output)
    data_source = "live"
    if fetch_type == "video":
        if uid is None:
            raise click.ClickException("video 模式需要 --uid")
        with BilibiliCollector() as collector:
            data = collector.fetch_user_videos(uid)
        account_id = str(uid)
        module = "bilibili-video"
    elif _is_mock_mode(demo):
        data = demo_bilibili_ranking(20)
        data_source = "demo"
        account_id = f"ranking_{rid}"
        module = "bilibili-ranking"
    else:
        with BilibiliCollector() as collector:
            data = collector.fetch_trending(rid=rid)
        account_id = f"ranking_{rid}"
        module = "bilibili-ranking"
    _maybe_save(data, "bilibili", account_id, save)
    raise SystemExit(
        _emit_output(
            data,
            resolved_fmt,
            module=module,
            data_source=data_source,
            output_file=output_file,
        )
    )


@fetch.command("bilibili-danmaku")
@click.option("--bvid", default=None, help="视频 BV 号")
@click.option("--aid", default=None, type=int, help="视频 AV 号")
@click.option("--cid", default=None, type=int, help="视频分 P cid")
@click.option("--limit", default=None, type=int, help="最多返回弹幕条数")
@click.option("--words", is_flag=True, help="输出高频词统计而非原始弹幕")
@click.option("--top", default=50, show_default=True, help="高频词 Top N（--words 模式）")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
def fetch_bilibili_danmaku(bvid, aid, cid, limit, words, top, output, save):
    """采集B站视频弹幕或弹幕高频词"""
    if not any([bvid, aid, cid]):
        raise click.ClickException("需要 --bvid、--aid 或 --cid 之一")
    with BilibiliCollector() as collector:
        if words:
            data = collector.fetch_danmaku_words(
                bvid=bvid, aid=aid, cid=cid, top_n=top, limit=limit
            )
            account_id = f"words_{bvid or aid or cid}"
        else:
            data = collector.fetch_video_danmaku(bvid=bvid, aid=aid, cid=cid, limit=limit)
            account_id = str(bvid or aid or cid)
    _output(data, output)
    _maybe_save(data, "bilibili_danmaku", account_id, save)


@fetch.command("live-danmaku")
@click.option("--room-id", required=True, type=int, help="直播间 room_id（短号/长号均可）")
@click.option("--duration", default=60, show_default=True, help="采集时长（秒）")
@click.option("--max-count", default=200, show_default=True, help="最多采集条数")
@click.option("--words", is_flag=True, help="输出高频词统计而非原始弹幕")
@click.option("--top", default=50, show_default=True, help="高频词 Top N（--words 模式）")
@click.option("--include-interact", is_flag=True, help="包含进场等互动消息")
@click.option(
    "--platform",
    default="bilibili",
    type=click.Choice(["bilibili"]),
    show_default=True,
    help="直播平台",
)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
def fetch_live_danmaku(room_id, duration, max_count, words, top, include_interact, platform, output, save):
    """采集直播间实时弹幕（当前支持 B站）"""
    if platform != "bilibili":
        raise click.ClickException(f"暂不支持平台: {platform}")
    with BilibiliCollector() as collector:
        if words:
            data = collector.fetch_live_danmaku_words(
                room_id, duration=duration, max_count=max_count, top_n=top
            )
            account_id = f"live_words_{room_id}"
        else:
            data = collector.fetch_live_danmaku(
                room_id,
                duration=duration,
                max_count=max_count,
                include_interact=include_interact,
            )
            account_id = f"live_{room_id}"
    _output(data, output)
    _maybe_save(data, "live_danmaku", account_id, save)


@fetch.command("bilibili-comments")
@click.option("--aid", type=int, default=None, help="视频 AV 号")
@click.option("--bvid", default=None, help="视频 BV 号")
@click.option("--limit", default=20, show_default=True)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_bilibili_comments(ctx, aid, bvid, limit, output, save):
    """采集B站视频热门评论"""
    if not aid and not bvid:
        raise click.ClickException("需要 --aid 或 --bvid")
    with BilibiliCollector(safe_mode=_safe_mode(ctx)) as collector:
        if not aid and bvid:
            meta = collector.resolve_video_cid(bvid=bvid)
            aid = int(meta["aid"])
            bvid = meta.get("bvid") or bvid
        data = collector.fetch_hot_comments(aid, limit=limit)
        account_id = f"comments_{bvid or aid}"
    _output(data, output)
    _maybe_save(data, "bilibili", account_id, save)


@fetch.command("bilibili-stat")
@click.option("--aid", type=int, default=None)
@click.option("--bvid", default=None)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_bilibili_stat(ctx, aid, bvid, output, save):
    """采集B站视频互动数据（播放/赞/投币/收藏等）"""
    if not aid and not bvid:
        raise click.ClickException("需要 --aid 或 --bvid")
    with BilibiliCollector(safe_mode=_safe_mode(ctx)) as collector:
        stat = collector.fetch_video_stat(bvid=bvid, aid=aid)
        data = [stat]
        account_id = f"stat_{stat.get('bvid') or aid}"
    _output(data, output)
    _maybe_save(data, "bilibili", account_id, save)


@fetch.command("douyin-comments")
@click.option("--aweme-id", required=True, help="抖音视频 ID")
@click.option("--limit", default=20, show_default=True)
@click.option("--cookie", default=None)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_douyin_comments(ctx, aweme_id, limit, cookie, output, save):
    """采集抖音视频评论"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("douyin-user", "douyin", cookie=cookie, skip=skip)
    use_cookie = get_cookie("douyin", cookie)
    with DouYinCollector(cookie=use_cookie, safe_mode=_safe_mode(ctx)) as collector:
        data = collector.fetch_video_comments(aweme_id, max_count=limit, cookie=use_cookie)
    _output(data, output)
    _maybe_save(data, "douyin", f"comments_{aweme_id}", save)


@fetch.command("xiaohongshu-search")
@click.option("--keyword", required=True, help="搜索关键词")
@click.option("--num", default=20, show_default=True)
@click.option("--cookie", default=None)
@click.option("--browser/--no-browser", default=None)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.option("--diff", is_flag=True)
@click.pass_context
def fetch_xiaohongshu_search(ctx, keyword, num, cookie, browser, output, save, diff):
    """按关键词搜索小红书笔记"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("xiaohongshu", "xiaohongshu", cookie=cookie, skip=skip)
    if diff and not save:
        raise click.ClickException("--diff 需要配合 --save 使用")
    use_cookie = get_cookie("xiaohongshu", cookie)
    with XiaoHongShuCollector(
        cookie=use_cookie, use_browser=browser, safe_mode=_safe_mode(ctx)
    ) as collector:
        data = collector.search_notes(keyword, num=num)
    account_id = f"topic:{keyword}"
    data = _save_with_diff(data, "xiaohongshu", account_id, diff, save)
    _output(data, output)


@fetch.command("xiaohongshu-comments")
@click.option("--note-id", required=True, help="笔记 ID")
@click.option("--limit", default=20, show_default=True)
@click.option("--cookie", default=None)
@click.option("--browser/--no-browser", default=None)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_xiaohongshu_comments(ctx, note_id, limit, cookie, browser, output, save):
    """采集小红书笔记评论"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("xiaohongshu", "xiaohongshu", cookie=cookie, skip=skip)
    use_cookie = get_cookie("xiaohongshu", cookie)
    with XiaoHongShuCollector(
        cookie=use_cookie, use_browser=browser, safe_mode=_safe_mode(ctx)
    ) as collector:
        data = collector.fetch_note_comments(note_id, limit=limit)
    _output(data, output)
    _maybe_save(data, "xiaohongshu", f"comments_{note_id}", save)


@fetch.command("zhihu-trending")
@click.option("--count", default=20, show_default=True, help="热榜条数")
@click.option("--format", "fmt", default=None, type=click.Choice(list(_FORMAT_CHOICES)))
@click.option("--output", "-o", default=None, help="输出文件路径（兼容旧版：json|csv|print 表示格式）")
@click.option("--demo", is_flag=True, help="使用内置示例数据，不访问外网")
@click.option("--save", is_flag=True)
@click.option("--diff", is_flag=True)
@click.pass_context
def fetch_zhihu_trending(ctx, count, fmt, output, demo, save, diff):
    """采集知乎热榜"""
    if diff and not save:
        raise click.ClickException("--diff 需要配合 --save 使用")
    resolved_fmt = _resolve_fmt(fmt, output)
    output_file = _resolve_output_file(output)
    if _is_mock_mode(demo):
        data = demo_zhihu_trending(count)
        data_source = "demo"
    else:
        try:
            with ZhihuCollector(cookie=get_cookie("zhihu")) as collector:
                data = collector.fetch_trending(max_count=count)
            data_source = "live"
        except Exception as e:
            logger.error("知乎热榜采集失败: %s", e)
            raise SystemExit(EXIT_SCRAPE_FAIL) from e
    data = _save_with_diff(data, "zhihu", "trending", diff, save)
    raise SystemExit(
        _emit_output(
            data,
            resolved_fmt,
            module="zhihu-trending",
            data_source=data_source,
            output_file=output_file,
        )
    )


@fetch.command("zhihu-answers")
@click.option("--question-id", required=True, help="知乎问题 ID")
@click.option("--count", default=10, show_default=True)
@click.option("--cookie", default=None)
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--save", is_flag=True)
@click.pass_context
def fetch_zhihu_answers(ctx, question_id, count, cookie, output, save):
    """采集知乎问题高赞回答"""
    skip = ctx.obj.get("skip_check", False)
    ensure_ready("zhihu-answers", "zhihu", cookie=cookie, skip=skip)
    with ZhihuCollector(cookie=get_cookie("zhihu", cookie)) as collector:
        data = collector.fetch_question_answers(question_id, max_count=count)
    _output(data, output)
    _maybe_save(data, "zhihu", question_id, save)


@cli.group()
def monitor():
    """监控编排：按 monitor.yaml 执行 daily / live 任务"""
    pass


@monitor.command("run")
@click.option("--task", type=click.Choice(["daily", "live"]), default="daily", show_default=True)
@click.option("--dry-run", is_flag=True, help="仅打印任务，不实际采集")
@click.option("--notify/--no-notify", default=None, help="有增量时发飞书（默认读 config）")
@click.pass_context
def monitor_run(ctx, task, dry_run, notify):
    """执行监控任务（读取 ~/.social-monitor/monitor.yaml）"""
    from social_monitor.config import init_monitor_config
    from social_monitor.monitor.runner import run_monitor_task
    from social_monitor.utils.cookie_manager import MONITOR_FILE

    if not MONITOR_FILE.exists():
        path = init_monitor_config()
        click.echo(f"已创建监控配置: {path}", err=True)

    summary = run_monitor_task(
        task=task,
        dry_run=dry_run,
        safe_mode=_safe_mode(ctx) or True,
        notify=notify,
    )
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get("errors"):
        raise SystemExit(1)


@monitor.command("routes")
@click.option("--json", "as_json", is_flag=True, help="JSON 输出")
def monitor_routes(as_json):
    """查看监控任务推荐采集路径（social-monitor vs Octopus）"""
    from social_monitor.monitor.config_loader import load_monitor_config
    from social_monitor.monitor.routes import list_task_routes, resolve_route

    monitor_cfg = load_monitor_config()
    rows = []
    for item in list_task_routes():
        resolved = resolve_route(item["key"], monitor_cfg)
        rows.append(resolved)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for row in rows:
        backend = row["backend"]
        mark = "→" if backend == row["recommended"] else "!"
        click.echo(
            f"{mark} {row['key']}: {backend} "
            f"(推荐 {row['recommended']}) | {row['label']}"
        )
        if backend == "octopus":
            click.echo(f"    模板: {row.get('octopus_template')}")
        else:
            click.echo(f"    CLI: {row['sm_cli_hint']}")


@monitor.command("init")
def monitor_init():
    """初始化 ~/.social-monitor/monitor.yaml"""
    from social_monitor.config import init_monitor_config

    path = init_monitor_config()
    click.echo(f"监控配置: {path}")


@cli.group("import")
def import_data():
    """导入外部采集结果"""
    pass


@import_data.command("octopus")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True))
@click.option("--platform", required=True, help="平台，如 douyin")
@click.option("--type", "content_type", default="live_danmaku", show_default=True)
@click.option("--room-id", default=None, help="直播间 ID，用于 account_id=live_{room_id}")
def import_octopus(file_path, platform, content_type, room_id):
    """导入 Octopus CLI 导出的 JSON 到 PostgreSQL"""
    from social_monitor.importers.octopus import import_octopus_file

    account_id = f"live_{room_id}" if room_id else f"octopus_{Path(file_path).stem}"
    count = import_octopus_file(
        Path(file_path),
        platform=platform,
        content_type=content_type,
        account_id=account_id,
    )
    click.echo(f"已入库 {count} 条 platform={platform} account={account_id}")


@cli.group()
def notify():
    """通知相关命令"""
    pass


@notify.command("feishu")
@click.option("--webhook", default=None, help="飞书 Webhook URL")
@click.option("--data", "data_file", required=True, type=click.Path(exists=True), help="JSON 数据文件")
@click.option("--platform", required=True, help="平台名称")
@click.option("--title", default="社交媒体监控", help="通知标题")
@click.option("--trending", is_flag=True, help="热榜通知格式")
def notify_feishu(webhook, data_file, platform, title, trending):
    """发送飞书通知"""
    config = load_config()
    webhook_url = webhook or config.get("feishu_webhook")
    if not webhook_url:
        raise click.ClickException("需要 --webhook 或在 config 中配置 feishu_webhook")

    with open(data_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    notifier = FeishuNotifier(webhook_url=webhook_url)
    try:
        if trending:
            notifier.notify_trending(platform, items)
        else:
            notifier.notify_new_content(platform, len(items), items[:5], account_name=title)
    finally:
        notifier.close()

    click.echo(f"已发送 {platform} 通知，共 {len(items)} 条")


@cli.group()
def config():
    """配置管理"""
    pass


@config.command("init")
def config_init():
    """初始化配置文件"""
    path = init_config()
    click.echo(f"配置文件已创建: {path}")


@config.command("show")
def config_show():
    """显示当前配置"""
    if not CONFIG_FILE.exists():
        click.echo("配置文件不存在，请先运行: social-monitor config init")
        return
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    click.echo(yaml.dump(config_data, allow_unicode=True, default_flow_style=False))


@config.command("check")
@click.argument(
    "platform",
    type=click.Choice(["weibo", "xiaohongshu", "douyin", "zhihu", "bilibili", "wechat", "all"]),
)
@click.option("--cookie", default=None, help="临时 Cookie 用于检测")
def config_check(platform, cookie):
    """检测平台 Cookie / 连通性"""
    platforms = (
        ["weibo", "xiaohongshu", "douyin", "zhihu", "bilibili", "wechat"]
        if platform == "all"
        else [platform]
    )
    all_ok = True
    for p in platforms:
        result = check_platform(p, cookie_override=cookie if platform != "all" else None)
        status = click.style("✓", fg="green") if result.ok else click.style("✗", fg="red")
        source = f" [{result.source}]" if result.source else ""
        click.echo(f"{status} {p}: {result.message}{source}")
        if not result.ok:
            all_ok = False
    if not all_ok:
        raise SystemExit(1)


@config.command("login")
@click.argument("platform", type=click.Choice(["xiaohongshu", "douyin"]))
@click.option("--timeout", default=300, show_default=True, help="等待登录秒数")
def config_login(platform, timeout):
    """打开浏览器手动登录（保存 Playwright 会话 + Cookie，推荐小红书/抖音）"""
    from social_monitor.utils.browser import browser_login

    try:
        browser_login(platform, wait_seconds=timeout)
        click.echo(f"登录流程结束，请运行: social-monitor config check {platform}")
    except ImportError as e:
        raise click.ClickException(str(e)) from e


@config.group("cookie")
def config_cookie():
    """Cookie 管理"""
    pass


@config_cookie.command("set")
@click.argument("platform", type=click.Choice(["weibo", "xiaohongshu", "douyin", "zhihu"]))
@click.option("--value", default=None, help="Cookie 字符串")
@click.option("--file", "cookie_file", type=click.Path(exists=True), help="从文件读取 Cookie")
def config_cookie_set(platform, value, cookie_file):
    """保存 Cookie 到 ~/.social-monitor/cookies/"""
    if cookie_file:
        value = Path(cookie_file).read_text(encoding="utf-8").strip()
    if not value:
        raise click.ClickException("需要 --value 或 --file")
    path = save_cookie(platform, value)
    click.echo(f"Cookie 已保存: {path}")


@config_cookie.command("show-source")
@click.argument("platform", type=click.Choice(["weibo", "xiaohongshu", "douyin", "zhihu"]))
def config_cookie_show_source(platform):
    """显示 Cookie 来源（脱敏）"""
    from social_monitor.utils.cookie_manager import mask_cookie

    source = get_cookie_source(platform)
    cookie = get_cookie(platform)
    click.echo(f"来源: {source}")
    click.echo(f"值: {mask_cookie(cookie or '')}")
    if has_browser_session(platform):
        click.echo(f"浏览器会话: 已存在 ({get_browser_dir(platform)})")


@cli.group()
def intel():
    """情报采集：批量热榜 + 增量对比"""
    pass


@intel.command("trending")
@click.option(
    "--platforms",
    default="weibo,douyin,zhihu,bilibili",
    show_default=True,
    help="逗号分隔平台",
)
@click.option("--count", default=20, show_default=True)
@click.option("--diff/--no-diff", default=True, help="仅输出相对历史的新增")
@click.option("--notify", is_flag=True, help="有新增时发送飞书通知")
@click.option("--webhook", default=None, help="飞书 Webhook（默认读配置）")
def intel_trending(platforms, count, diff, notify, webhook):
    """批量采集热榜并增量对比（情报场景推荐）"""
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    config = load_config()
    storage, _ = get_storage()
    webhook_url = webhook or config.get("feishu_webhook")

    try:
        summary = {}
        for name in platform_list:
            try:
                click.echo(f"采集 {name} 热榜...", err=True)
                if name == "weibo":
                    with WeiboCollector() as c:
                        data = c.fetch_trending(max_count=count)
                elif name == "douyin":
                    with DouYinCollector() as c:
                        data = c.fetch_trending(max_count=count)
                elif name == "zhihu":
                    with ZhihuCollector() as c:
                        data = c.fetch_trending(max_count=count)
                elif name == "bilibili":
                    with BilibiliCollector() as c:
                        data = c.fetch_trending(rid=0)[:count]
                else:
                    click.echo(f"跳过未知平台: {name}", err=True)
                    continue

                account_id = "trending"
                if diff:
                    added, _, prev = load_and_diff(storage, name, account_id, data)
                    summary[name] = {"total": len(data), "new": len(added), "items": added}
                    click.echo(f"  {name}: 共 {len(data)} 条，新增 {len(added)} 条", err=True)
                else:
                    storage.save(name, account_id, data)
                    summary[name] = {"total": len(data), "new": len(data), "items": data}
            except Exception as e:
                click.echo(f"  {name} 失败: {e}", err=True)
                summary[name] = {"error": str(e)}

        click.echo(json.dumps(summary, ensure_ascii=False, indent=2))

        if notify and webhook_url:
            notifier = FeishuNotifier(webhook_url=webhook_url)
            try:
                for name, info in summary.items():
                    if info.get("new", 0) > 0:
                        notifier.notify_trending(name, info["items"])
            finally:
                notifier.close()
            click.echo("飞书通知已发送", err=True)
        elif notify:
            click.echo("未配置 feishu_webhook，跳过通知", err=True)
    finally:
        close_storage(storage)


@cli.group()
def account():
    """账号 registry：批量解析 account_id"""
    pass


@account.command("resolve-p0")
@click.option(
    "--registry",
    "registry_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="账号清单 markdown，默认 guide/监控渠道-账号.md",
)
@click.option("--priority", default="P0", show_default=True, help="优先级过滤")
@click.option(
    "--platform",
    "platform_key",
    default=None,
    help="仅解析指定平台 key：bilibili/douyin/wechat/xiaohongshu",
)
@click.option(
    "--output",
    "-o",
    "output_fmt",
    type=click.Choice(["json", "monitor-yaml"]),
    default="json",
    show_default=True,
)
@click.option("--out-file", type=click.Path(), default=None, help="写入文件（默认 stdout）")
@click.option("--apply", is_flag=True, help="将 resolved 的 account_id 写回 registry markdown")
@click.option("--safe/--no-safe", default=True, help="安全模式请求间隔")
@click.option(
    "--login/--skip-login",
    default=True,
    help="解析前检测抖音/小红书登录态，未登录时提示并打开浏览器",
)
@click.pass_context
def account_resolve_p0(ctx, registry_path, priority, platform_key, output_fmt, out_file, apply, safe, login):
    """从各平台搜索页批量解析 P0（或指定优先级）账号 ID"""
    from pathlib import Path

    from social_monitor.account.registry import (
        apply_resolved_ids,
        default_registry_path,
        filter_entries,
        load_registry,
    )
    from social_monitor.account.resolvers import build_monitor_yaml_snippet, resolve_entries
    from social_monitor.account.auth import ensure_login_for_entries

    path = Path(registry_path) if registry_path else default_registry_path()
    entries = filter_entries(
        load_registry(path),
        priority=priority,
        platform_key=platform_key,
        only_pending=True,
    )
    if not entries:
        raise click.ClickException(f"无待解析条目 priority={priority}")

    if login:
        ensure_login_for_entries(entries, interactive=True)

    click.echo(f"待解析 {len(entries)} 条（priority={priority}）", err=True)
    results = resolve_entries(entries, safe_mode=safe)

    resolved = sum(1 for r in results if r.get("resolve_status") == "resolved")
    click.echo(f"成功 {resolved}/{len(results)}", err=True)

    if output_fmt == "monitor-yaml":
        payload = build_monitor_yaml_snippet(results)
    else:
        payload = json.dumps(results, ensure_ascii=False, indent=2)

    if out_file:
        Path(out_file).write_text(payload, encoding="utf-8")
        click.echo(f"已写入 {out_file}", err=True)
    else:
        click.echo(payload)

    if apply:
        count = apply_resolved_ids(path, results)
        click.echo(f"已更新 registry {count} 处 account_id", err=True)


def main() -> int:
    try:
        cli(standalone_mode=False)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return EXIT_OK
        if isinstance(code, int):
            return code
        return EXIT_ERROR
    except click.ClickException:
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
