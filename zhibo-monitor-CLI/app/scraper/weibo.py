import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from app.scraper.base import BaseScraper


class WeiboScraper(BaseScraper):
    def __init__(
        self,
        room_id: str,
        event_name: str | None = None,
        car_brand: str | None = None,
        car_model: str | None = None,
        event_id: str | None = None,
        headless: bool = True,
    ):
        auth_file = os.path.join(os.getcwd(), "auth", "weibo_state.json")
        storage_state = auth_file if os.path.exists(auth_file) else None

        super().__init__(
            room_id=room_id,
            platform="weibo",
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id,
            headless=headless,
            storage_state=storage_state,
        )
        self.url = f"https://weibo.com/l/wblive/p/show/{room_id}"
        self.danmaku_buffer: List[Dict[str, str]] = []
        self.last_msg_texts: set[str] = set()
        self.latest_online_count = 0
        self.status_mid: Optional[str] = None
        self.anchor_uid: Optional[int] = None
        self.im_token_ok = False
        self._seen_comment_ids: set[str] = set()
        self._last_metric_log_at = 0.0

    async def _fetch_json(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self.page.evaluate(
                """async (path) => {
                  const resp = await fetch(path, { credentials: 'include' });
                  const text = await resp.text();
                  try { return JSON.parse(text); } catch { return { _raw: text.slice(0, 500) }; }
                }""",
                path,
            )
            if isinstance(result, dict):
                return result
        except Exception as exc:
            print(f"[{self.platform}] API 请求失败 {path}: {exc}")
        return None

    async def _load_room_meta(self) -> bool:
        data = await self._fetch_json(
            f"/l/!/2/wblive/room/show_pc_live.json?live_id={self.room_id}"
        )
        if not data or data.get("code") != 100000:
            print(f"[{self.platform}] 无法获取直播间信息: {data}")
            return False

        room = data.get("data") or {}
        self.status_mid = str(room.get("mid") or "")
        user = room.get("user") or {}
        self.anchor_uid = user.get("uid")
        title = room.get("title") or ""
        status = room.get("status")
        print(
            f"[{self.platform}] 直播间: {title} | 状态={status} | mid={self.status_mid} | 主播uid={self.anchor_uid}"
        )
        return bool(self.status_mid)

    async def _check_im_login(self) -> bool:
        token_resp = await self._fetch_json(
            f"/l/!/2/wblive/room/get_access_token.json?live_id={self.room_id}"
        )
        if not token_resp:
            return False
        if token_resp.get("code") == 100006:
            print(f"[{self.platform}] 直播 IM 未登录: {token_resp.get('msg')}，弹幕仅采集评论区")
            return False
        if token_resp.get("code") == 100000:
            print(f"[{self.platform}] 直播 IM 登录态有效，可采集实时互动")
            return True
        print(f"[{self.platform}] IM token 响应: {token_resp}")
        return False

    async def _ensure_playing(self) -> None:
        play_btn = self.page.locator(
            ".wbpv-big-play-button, .vjs-big-play-button, button[aria-label*='播放']"
        )
        if await play_btn.count() > 0:
            print(f"[{self.platform}] 点击播放按钮以激活直播流")
            await play_btn.first.click()
            await asyncio.sleep(3)

    async def _get_online_count(self) -> int:
        data = await self._fetch_json(f"/l/lua/pc/room/status?live_id={self.room_id}")
        if not data or data.get("code") != 100000:
            return self.latest_online_count
        count = int((data.get("data") or {}).get("count") or 0)
        return count

    async def _fetch_comments(self) -> List[Dict[str, str]]:
        if not self.status_mid or not self.anchor_uid:
            return []

        path = (
            f"/ajax/statuses/buildComments?is_reload=1&id={self.status_mid}"
            f"&is_show_bulletin=2&is_mix=0&max_id=0&count=50&uid={self.anchor_uid}"
        )
        data = await self._fetch_json(path)
        if not data or data.get("ok") != 1:
            return []

        comments: List[Dict[str, str]] = []
        for item in data.get("data") or []:
            cid = str(item.get("id") or "")
            user = item.get("user") or {}
            user_name = (user.get("screen_name") or user.get("name") or "").strip()
            content = (item.get("text_raw") or item.get("text") or "").strip()
            content = re.sub(r"<[^>]+>", "", content)
            if not cid or not user_name or not content:
                continue
            if cid in self._seen_comment_ids:
                continue
            self._seen_comment_ids.add(cid)
            comments.append({"user_name": user_name, "content": content})
        return comments

    def _register_im_listener(self) -> None:
        async def on_response(response) -> None:
            if "liveim-pc.api.weibo.com/wesync" not in response.url:
                return
            try:
                body = await response.text()
                payload = json.loads(body)
            except Exception:
                return

            body = payload.get("body") or {}
            if body.get("error_code"):
                return

            messages = body.get("messages") or body.get("msgs") or []
            if isinstance(body.get("message"), dict):
                messages = [body["message"]]

            new_items: List[Dict[str, str]] = []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                user_name = (
                    msg.get("sender_name")
                    or msg.get("nickname")
                    or (msg.get("user") or {}).get("screen_name")
                    or ""
                ).strip()
                content = (msg.get("content") or msg.get("text") or msg.get("msg") or "").strip()
                if not user_name or not content:
                    continue
                msg_hash = f"{user_name}::{content}"
                if msg_hash in self.last_msg_texts:
                    continue
                self.last_msg_texts.add(msg_hash)
                new_items.append({"user_name": user_name, "content": content})

            if new_items:
                self.danmaku_buffer.extend(new_items)
                print(f"[{self.platform}] IM 抓取到 {len(new_items)} 条新消息")

        self.page.on("response", lambda resp: asyncio.create_task(on_response(resp)))

    async def run_loop(self):
        await self.start()

        if not self.storage_state:
            print(
                f"[{self.platform}] 警告: 未找到 auth/weibo_state.json，"
                "建议先运行 `python main.py login weibo`"
            )

        try:
            print(f"[{self.platform}] 正在打开: {self.url}")
            await self.page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)

            if not await self._load_room_meta():
                await self.stop()
                return

            self.im_token_ok = await self._check_im_login()
            self._register_im_listener()
            await self._ensure_playing()

            screenshot = os.path.join(os.getcwd(), "weibo_debug.png")
            await self.page.screenshot(path=screenshot, full_page=True)
            print(f"[{self.platform}] 调试截图: {screenshot}")

        except Exception as exc:
            print(f"[{self.platform}] 打开页面失败: {exc}")
            await self.stop()
            return

        loop_count = 0
        while self.is_running:
            try:
                loop_count += 1
                new_items: List[Dict[str, str]] = []

                comments = await self._fetch_comments()
                for msg in comments:
                    msg_hash = f"{msg['user_name']}::{msg['content']}"
                    if msg_hash not in self.last_msg_texts:
                        self.last_msg_texts.add(msg_hash)
                        new_items.append(msg)

                if new_items:
                    self.danmaku_buffer.extend(new_items)
                    print(f"[{self.platform}] 评论区抓取 {len(new_items)} 条")

                online_count = await self._get_online_count()
                if online_count > 0:
                    if online_count != self.latest_online_count:
                        print(f"[{self.platform}] 在线人数: {online_count}")
                    self.latest_online_count = online_count
                elif loop_count % 15 == 0:
                    print(f"[{self.platform}] 轮询中... 在线={self.latest_online_count} 缓冲={len(self.danmaku_buffer)}")

                should_flush = (
                    len(self.danmaku_buffer) >= 5
                    or (self.danmaku_buffer and loop_count % 10 == 0)
                    or (self.latest_online_count > 0 and loop_count % 5 == 0)
                )
                if should_flush:
                    self._flush_to_db(self.latest_online_count)

                if len(self.last_msg_texts) > 3000:
                    self.last_msg_texts = set(list(self.last_msg_texts)[-1500:])

            except Exception as exc:
                print(f"[{self.platform}] 抓取循环异常: {exc}")

            await asyncio.sleep(3)

        if self.danmaku_buffer:
            self._flush_to_db(self.latest_online_count)
        await self.stop()

    def _flush_to_db(self, current_online_count: int):
        try:
            self.flush_danmaku_records(
                danmakus=self.danmaku_buffer,
                online_count=current_online_count,
                like_count=0,
            )
            if self.danmaku_buffer:
                print(
                    f"[{self.platform}] 落库 {len(self.danmaku_buffer)} 条，"
                    f"在线人数 {current_online_count}"
                )
            self.danmaku_buffer.clear()
        except Exception as exc:
            print(f"[{self.platform}] 落库失败: {exc}")
