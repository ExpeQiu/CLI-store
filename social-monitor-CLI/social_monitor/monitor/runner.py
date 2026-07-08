"""监控任务编排"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from social_monitor.config import get_monitor_settings, get_rsshub_url
from social_monitor.monitor.config_loader import load_monitor_config, normalize_accounts
from social_monitor.monitor.octopus_runner import (
    OctopusRunError,
    import_octopus_route,
    route_detail_for_log,
    run_octopus_collect,
)
from social_monitor.monitor.routes import BACKEND_OCTOPUS, BACKEND_SM, resolve_backend, resolve_route
from social_monitor.notifiers.feishu import FeishuNotifier
from social_monitor.platforms.bilibili import BilibiliCollector
from social_monitor.platforms.douyin import DouYinCollector
from social_monitor.platforms.wechat import WeChatCollector
from social_monitor.platforms.weibo import WeiboCollector
from social_monitor.platforms.xiaohongshu import XiaoHongShuCollector
from social_monitor.storage.factory import close_storage, get_storage
from social_monitor.utils.cookie_checker import check_platform
from social_monitor.utils.cookie_manager import LIVE_STATE_DIR, get_cookie, load_config
from social_monitor.utils.diff_helper import load_and_diff
from social_monitor.utils.errors import ScrapeBlockedError
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class MonitorRunner:
    """按 monitor.yaml 执行 daily / live 任务"""

    def __init__(
        self,
        dry_run: bool = False,
        safe_mode: bool = True,
        notify: Optional[bool] = None,
    ):
        self.dry_run = dry_run
        self.safe_mode = safe_mode
        self.monitor_cfg = load_monitor_config()
        self.app_cfg = load_config()
        self.settings = get_monitor_settings()
        self.notify = notify if notify is not None else self.settings.get("feishu_on_diff", True)
        self.skip_on_fail = self.settings.get("skip_on_check_fail", True)
        self.summary: Dict[str, Any] = {"tasks": [], "errors": []}
        self._notify_items: List[tuple] = []

    def _log_task(self, name: str, status: str, detail: str = "") -> None:
        entry = {"task": name, "status": status, "detail": detail}
        self.summary["tasks"].append(entry)
        logger.info("monitor task=%s status=%s %s", name, status, detail)

    def _check_platform(self, platform: str) -> bool:
        result = check_platform(platform)
        if result.ok:
            return True
        msg = f"{platform} 未就绪: {result.message}"
        self.summary["errors"].append(msg)
        if self.skip_on_fail:
            self._log_task(f"check:{platform}", "skip", msg)
            return False
        raise RuntimeError(msg)

    def _save_diff(
        self,
        platform: str,
        account_id: str,
        data: List[Dict[str, Any]],
        storage,
    ) -> List[Dict[str, Any]]:
        if not data:
            return []
        added, _, prev = load_and_diff(storage, platform, account_id, data)
        self._log_task(
            f"{platform}:{account_id}",
            "ok",
            f"历史 {prev} 本次 {len(data)} 新增 {len(added)}",
        )
        if added and self.notify:
            self._notify_items.append((platform, account_id, added))
        return added

    def _save_xhs_comments(
        self,
        note_id: str,
        fetch_fn: Callable[[], List[Dict[str, Any]]],
        storage,
    ) -> List[Dict[str, Any]]:
        comments = fetch_fn()
        if comments:
            storage.save(
                "xiaohongshu",
                f"comments_{note_id}",
                comments,
                mode="replace",
            )
        return comments

    def _diff_by_id(
        self,
        prev: List[Dict[str, Any]],
        new: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        prev_ids = {str(item.get("id") or item.get("note_id", "")) for item in prev}
        added = []
        for item in new:
            item_id = str(item.get("id") or item.get("note_id", ""))
            if item_id and item_id not in prev_ids:
                added.append(item)
        return added

    def _route_backend(self, route_key: str) -> str:
        return resolve_backend(route_key, self.monitor_cfg)

    def _route_log_suffix(self, route_key: str) -> str:
        return route_detail_for_log(route_key, self.monitor_cfg)

    def _octopus_output(self, route_key: str, suffix: str) -> Path:
        safe = route_key.replace(":", "_")
        return LIVE_STATE_DIR / f"octopus_{safe}_{suffix}.json"

    def _run_octopus_task(
        self,
        route_key: str,
        ctx: Dict[str, Any],
        account_id: str,
        storage,
        mode: str = "append",
        timeout: int = 3600,
    ) -> int:
        out = self._octopus_output(route_key, account_id.replace(":", "_"))
        run_octopus_collect(route_key, self.monitor_cfg, out, ctx, timeout=timeout)
        return import_octopus_route(
            route_key,
            self.monitor_cfg,
            out,
            account_id,
            storage=storage,
            mode=mode,
        )

    def _run_with_route(
        self,
        route_key: str,
        sm_callable: Callable[[], Any],
        octopus_ctx: Dict[str, Any],
        account_id: str,
        storage,
        octopus_mode: str = "append",
        on_octopus_count: Optional[Callable[[int], None]] = None,
    ) -> Any:
        """按路由执行 social-monitor 或 Octopus，支持回退"""
        route = resolve_route(route_key, self.monitor_cfg)
        backend = route["backend"]
        fallback = route.get("fallback")

        if backend == BACKEND_SM:
            return sm_callable()

        try:
            count = self._run_octopus_task(
                route_key, octopus_ctx, account_id, storage, mode=octopus_mode
            )
            if on_octopus_count:
                on_octopus_count(count)
            return count
        except OctopusRunError as e:
            if fallback == BACKEND_SM:
                logger.warning("Octopus 失败，回退 social-monitor route=%s: %s", route_key, e)
                self._log_task(route_key, "fallback", str(e))
                return sm_callable()
            raise

    def _save_replace(
        self,
        platform: str,
        account_id: str,
        data: List[Dict[str, Any]],
        storage,
    ) -> None:
        if not data:
            return
        storage.save(platform, account_id, data, mode="replace")
        self._log_task(f"{platform}:{account_id}", "ok", f"快照 {len(data)} 条")

    def run_daily(self) -> Dict[str, Any]:
        storage, _ = get_storage()
        try:
            self._run_weibo_daily(storage)
            self._run_wechat_daily(storage)
            self._run_bilibili_daily(storage)
            self._run_douyin_daily(storage)
            self._run_xiaohongshu_daily(storage)
            self._send_notifications()
        except ScrapeBlockedError as e:
            self.summary["errors"].append(str(e))
            logger.error("日任务中断: %s", e)
        finally:
            close_storage(storage)
        return self.summary

    def run_live(self) -> Dict[str, Any]:
        storage, _ = get_storage()
        try:
            self._run_bilibili_live(storage)
            self._run_douyin_live(storage)
        except ScrapeBlockedError as e:
            self.summary["errors"].append(str(e))
        finally:
            close_storage(storage)
        return self.summary

    def _run_weibo_daily(self, storage) -> None:
        section = self.monitor_cfg.get("weibo") or {}
        pages = int(section.get("pages", 1))

        trending = section.get("trending") or {}
        if trending.get("enabled", True):
            today = date.today().isoformat()
            account_id = f"trending_{today}"
            name = f"weibo:trending:{today}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"fetch weibo-trending --save | {self._route_log_suffix('weibo:trending')}",
                )
            elif not self._check_platform("weibo"):
                pass
            else:
                with WeiboCollector(safe_mode=self.safe_mode) as c:
                    data = c.fetch_trending(max_count=50)
                self._save_replace("weibo", account_id, data, storage)

        for uid in section.get("accounts") or []:
            uid = str(uid)
            name = f"weibo:user:{uid}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"pages={pages} | {self._route_log_suffix('weibo:user_timeline')}",
                )
                continue
            if not self._check_platform("weibo"):
                continue
            with WeiboCollector(cookie=get_cookie("weibo"), safe_mode=self.safe_mode) as c:
                data = c.fetch_user_timeline(uid, max_page=pages)
            self._save_diff("weibo", uid, data, storage)

    def _run_wechat_daily(self, storage) -> None:
        section = self.monitor_cfg.get("wechat") or {}
        for wxid in section.get("accounts") or []:
            wxid = str(wxid)
            name = f"wechat:{wxid}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"fetch wechat | {self._route_log_suffix('wechat:articles')}",
                )
                continue
            if not self._check_platform("wechat"):
                continue
            url = get_rsshub_url()
            with WeChatCollector(rsshub_url=url, safe_mode=self.safe_mode) as c:
                try:
                    data = c.fetch_via_rsshub(wxid)
                except RuntimeError as e:
                    self.summary["errors"].append(str(e))
                    self._log_task(name, "error", str(e))
                    continue
            self._save_diff("wechat", wxid, data, storage)

    def _run_bilibili_daily(self, storage) -> None:
        section = self.monitor_cfg.get("bilibili") or {}
        comments_limit = int(section.get("comments_limit", 20))
        do_danmaku = section.get("video_danmaku", True)

        for raw in normalize_accounts(section):
            uid = raw if not isinstance(raw, dict) else raw.get("uid")
            if uid is None:
                continue
            uid = int(uid)
            name = f"bilibili:uid:{uid}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"videos+comments+danmaku | {self._route_log_suffix('bilibili:videos')}",
                )
                continue
            if not self._check_platform("bilibili"):
                continue

            with BilibiliCollector(safe_mode=self.safe_mode) as c:
                videos = c.fetch_user_videos(uid)
            added_videos, _, _ = load_and_diff(storage, "bilibili", str(uid), videos)

            for video in added_videos:
                bvid = video.get("bvid") or video.get("id")
                if not bvid:
                    continue
                with BilibiliCollector(safe_mode=self.safe_mode) as c:
                    try:
                        stat = c.fetch_video_stat(bvid=bvid)
                        storage.save("bilibili", f"stat_{bvid}", [stat], mode="replace")
                    except Exception as e:
                        logger.warning("B站 stat 失败 bvid=%s: %s", bvid, e)

                    if do_danmaku:
                        try:
                            words = c.fetch_danmaku_words(bvid=bvid, top_n=30)
                            storage.save("bilibili", f"words_{bvid}", words, mode="replace")
                        except Exception as e:
                            logger.warning("B站弹幕词失败 bvid=%s: %s", bvid, e)

                    try:
                        meta = c.resolve_video_cid(bvid=bvid)
                        aid = meta.get("aid")
                        if aid:
                            comments = c.fetch_hot_comments(int(aid), limit=comments_limit)
                            storage.save(
                                "bilibili",
                                f"comments_{bvid}",
                                comments,
                                mode="replace",
                            )
                    except Exception as e:
                        logger.warning("B站评论失败 bvid=%s: %s", bvid, e)

            self._log_task(name, "ok", f"视频 {len(videos)} 新增 {len(added_videos)}")

    def _run_douyin_daily(self, storage) -> None:
        section = self.monitor_cfg.get("douyin") or {}
        do_comments = section.get("comments", False)

        for raw in normalize_accounts(section):
            sec_uid = raw if not isinstance(raw, dict) else raw.get("sec_uid")
            if not sec_uid:
                continue
            sec_uid = str(sec_uid)
            name = f"douyin:{sec_uid}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"fetch douyin videos | {self._route_log_suffix('douyin:videos')}",
                )
                continue
            cookie = get_cookie("douyin")
            if not cookie:
                self._log_task(name, "skip", "未配置 Cookie")
                continue
            if not self._check_platform("douyin"):
                continue

            with DouYinCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                videos = c.fetch_user_videos(sec_uid, cookie=cookie)
            added, _, _ = load_and_diff(storage, "douyin", sec_uid, videos)

            if do_comments:
                for video in added:
                    aweme_id = video.get("id")
                    if not aweme_id:
                        continue
                    comment_route = "douyin:comments"
                    aweme_id = str(aweme_id)

                    def _sm_comments():
                        with DouYinCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                            comments = c.fetch_video_comments(aweme_id, cookie=cookie)
                        if comments:
                            storage.save(
                                "douyin",
                                f"comments_{aweme_id}",
                                comments,
                                mode="replace",
                            )
                        return comments

                    try:
                        self._run_with_route(
                            comment_route,
                            _sm_comments,
                            {"aweme_id": aweme_id},
                            f"comments_{aweme_id}",
                            storage,
                            octopus_mode="replace",
                        )
                    except OctopusRunError as e:
                        self.summary["errors"].append(str(e))
                        self._log_task(f"douyin:comments:{aweme_id}", "error", str(e))

            self._log_task(name, "ok", f"视频 {len(videos)} 新增 {len(added)}")

    def _run_xiaohongshu_daily(self, storage) -> None:
        section = self.monitor_cfg.get("xiaohongshu") or {}
        notes_per = int(section.get("notes_per_topic", 20))
        comments_per = int(section.get("comments_per_note", 20))
        topics = section.get("topics") or []
        users = section.get("users") or []

        if self.dry_run:
            for t in topics:
                self._log_task(
                    f"xhs:topic:{t}",
                    "dry-run",
                    f"search+comments | {self._route_log_suffix('xiaohongshu:topic_search')}",
                )
            for u in users:
                self._log_task(
                    f"xhs:user:{u}",
                    "dry-run",
                    f"notes+comments | {self._route_log_suffix('xiaohongshu:user_notes')}",
                )
            return

        if not self._check_platform("xiaohongshu"):
            return

        cookie = get_cookie("xiaohongshu")
        topic_route = "xiaohongshu:topic_search"
        user_route = "xiaohongshu:user_notes"
        comment_route = "xiaohongshu:comments"

        for keyword in topics:
            account_id = f"topic:{keyword}"

            def _sm_topic():
                with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                    return c.search_notes(keyword, num=notes_per)

            try:
                if self._route_backend(topic_route) == BACKEND_OCTOPUS:
                    prev_notes = storage.load("xiaohongshu", account_id) or []
                    self._run_octopus_task(
                        topic_route,
                        {"keyword": keyword},
                        account_id,
                        storage,
                        mode="replace",
                    )
                    notes = storage.load("xiaohongshu", account_id) or []
                    added = self._diff_by_id(prev_notes, notes)
                else:
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        notes = c.search_notes(keyword, num=notes_per)
                    added, _, _ = load_and_diff(storage, "xiaohongshu", account_id, notes)
            except OctopusRunError as e:
                route = resolve_route(topic_route, self.monitor_cfg)
                if route.get("fallback") == BACKEND_SM:
                    logger.warning("小红书主题 Octopus 失败，回退 sm: %s", e)
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        notes = c.search_notes(keyword, num=notes_per)
                    added, _, _ = load_and_diff(storage, "xiaohongshu", account_id, notes)
                else:
                    self.summary["errors"].append(str(e))
                    self._log_task(f"xhs:topic:{keyword}", "error", str(e))
                    continue

            for note in added:
                note_id = note.get("note_id") or note.get("id")
                if not note_id:
                    continue
                note_id = str(note_id)

                def _sm_note_comments():
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        return c.fetch_note_comments(note_id, limit=comments_per)

                try:
                    self._run_with_route(
                        comment_route,
                        lambda: self._save_xhs_comments(note_id, _sm_note_comments, storage),
                        {"note_id": note_id},
                        f"comments_{note_id}",
                        storage,
                        octopus_mode="replace",
                    )
                except OctopusRunError as e:
                    self.summary["errors"].append(str(e))
                    self._log_task(f"xhs:comments:{note_id}", "error", str(e))

            self._log_task(f"xhs:topic:{keyword}", "ok", f"帖 {len(notes)} 新增 {len(added)}")

        for user_id in users:
            user_id = str(user_id)

            def _sm_user_notes():
                with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                    return c.fetch_user_notes(user_id, num=notes_per)

            try:
                if self._route_backend(user_route) == BACKEND_OCTOPUS:
                    prev_notes = storage.load("xiaohongshu", user_id) or []
                    self._run_octopus_task(
                        user_route,
                        {"user_id": user_id},
                        user_id,
                        storage,
                        mode="replace",
                    )
                    notes = storage.load("xiaohongshu", user_id) or []
                    added = self._diff_by_id(prev_notes, notes)
                else:
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        notes = c.fetch_user_notes(user_id, num=notes_per)
                    added, _, _ = load_and_diff(storage, "xiaohongshu", user_id, notes)
            except OctopusRunError as e:
                route = resolve_route(user_route, self.monitor_cfg)
                if route.get("fallback") == BACKEND_SM:
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        notes = c.fetch_user_notes(user_id, num=notes_per)
                    added, _, _ = load_and_diff(storage, "xiaohongshu", user_id, notes)
                else:
                    self.summary["errors"].append(str(e))
                    self._log_task(f"xhs:user:{user_id}", "error", str(e))
                    continue

            for note in added:
                note_id = note.get("note_id") or note.get("id")
                if not note_id:
                    continue
                note_id = str(note_id)

                def _sm_user_comments():
                    with XiaoHongShuCollector(cookie=cookie, safe_mode=self.safe_mode) as c:
                        return c.fetch_note_comments(note_id, limit=comments_per)

                try:
                    self._run_with_route(
                        comment_route,
                        lambda: self._save_xhs_comments(note_id, _sm_user_comments, storage),
                        {"note_id": note_id},
                        f"comments_{note_id}",
                        storage,
                        octopus_mode="replace",
                    )
                except OctopusRunError as e:
                    self.summary["errors"].append(str(e))
                    self._log_task(f"xhs:comments:{note_id}", "error", str(e))

            self._log_task(f"xhs:user:{user_id}", "ok", f"帖 {len(notes)} 新增 {len(added)}")

    def _live_state_file(self, platform: str, room_id: int) -> Path:
        LIVE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return LIVE_STATE_DIR / f"{platform}_{room_id}.json"

    def _was_live(self, platform: str, room_id: int) -> bool:
        f = self._live_state_file(platform, room_id)
        if not f.exists():
            return False
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("live_status") == 1
        except (json.JSONDecodeError, OSError):
            return False

    def _set_live_state(self, platform: str, room_id: int, live_status: int) -> None:
        f = self._live_state_file(platform, room_id)
        f.write_text(json.dumps({"live_status": live_status}), encoding="utf-8")

    def _run_bilibili_live(self, storage) -> None:
        section = self.monitor_cfg.get("bilibili") or {}
        duration = int(section.get("live_duration", 1800))
        max_count = int(section.get("live_max_count", 5000))

        for room_id in section.get("live_rooms") or []:
            room_id = int(room_id)
            name = f"bilibili:live:{room_id}"
            if self.dry_run:
                self._log_task(
                    name,
                    "dry-run",
                    f"check live_status | {self._route_log_suffix('bilibili:live_danmaku')}",
                )
                continue

            with BilibiliCollector(safe_mode=self.safe_mode) as c:
                try:
                    info = c.fetch_live_room_info(room_id)
                except Exception as e:
                    self._log_task(name, "error", str(e))
                    continue

                is_live = info.get("live_status") == 1
                was_live = self._was_live("bilibili", room_id)

                if is_live and not was_live:
                    self._log_task(name, "start", info.get("title", ""))
                    data = c.fetch_live_danmaku(
                        room_id, duration=duration, max_count=max_count
                    )
                    if data:
                        storage.save("live_danmaku", f"live_{room_id}", data, mode="append")
                elif not is_live and was_live:
                    self._log_task(name, "end", "下播")

                self._set_live_state("bilibili", room_id, info.get("live_status", 0))

    def _run_douyin_live(self, storage) -> None:
        route_key = "douyin:live_danmaku"

        for room_id in (self.monitor_cfg.get("douyin") or {}).get("live_rooms") or []:
            room_id = str(room_id)
            name = f"douyin:live:{room_id}"
            if self.dry_run:
                self._log_task(name, "dry-run", self._route_log_suffix(route_key))
                continue

            try:
                count = self._run_octopus_task(
                    route_key,
                    {"room_id": room_id},
                    f"live_{room_id}",
                    storage,
                    mode="append",
                )
                self._log_task(name, "ok", f"Octopus 入库 {count} 条")
            except OctopusRunError as e:
                route = resolve_route(route_key, self.monitor_cfg)
                if route.get("fallback"):
                    self._log_task(name, "error", str(e))
                else:
                    self._log_task(name, "skip", str(e))
                self.summary["errors"].append(str(e))

    def _send_notifications(self) -> None:
        webhook = self.app_cfg.get("feishu_webhook")
        if not self.notify or not webhook or not self._notify_items:
            return
        notifier = FeishuNotifier(webhook_url=webhook)
        try:
            for platform, account_id, items in self._notify_items:
                notifier.notify_new_content(
                    platform,
                    len(items),
                    items,
                    account_name=account_id,
                )
            self._log_task("feishu", "ok", f"通知 {len(self._notify_items)} 批")
        finally:
            notifier.close()


def run_monitor_task(
    task: str,
    dry_run: bool = False,
    safe_mode: bool = True,
    notify: Optional[bool] = None,
) -> Dict[str, Any]:
    runner = MonitorRunner(dry_run=dry_run, safe_mode=safe_mode, notify=notify)
    if task == "daily":
        return runner.run_daily()
    if task == "live":
        return runner.run_live()
    raise ValueError(f"未知任务: {task}")
