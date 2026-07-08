import asyncio
import re
import time
from typing import Dict, List

from app.scraper.base import BaseScraper


class DouyinScraper(BaseScraper):
    def __init__(
        self,
        room_id: str,
        event_name: str | None = None,
        car_brand: str | None = None,
        car_model: str | None = None,
        event_id: str | None = None,
        headless: bool = True,
    ):
        super().__init__(
            room_id=room_id,
            platform="douyin",
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id,
            headless=headless,
        )
        self.url = f"https://live.douyin.com/{room_id}"
        self.danmaku_buffer: List[Dict[str, str]] = []
        self.last_msg_texts: set[str] = set()
        self.last_metric_flush_at = 0.0
        self.metric_flush_interval_seconds = 30.0

    async def start(self):
        await super().start()
        await self.page.goto(self.url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)
        print(f"[{self.platform}] 已打开抖音直播间: {self.room_id}")

    async def run_loop(self):
        await self.start()

        while self.is_running:
            online_count = 0
            like_count = 0
            try:
                new_danmakus = await self._extract_messages()
                if new_danmakus:
                    self.danmaku_buffer.extend(new_danmakus)
                    print(f"[{self.platform}] 抓取到 {len(new_danmakus)} 条新消息")

                metrics = await self._extract_metrics()
                online_count = metrics["online_count"]
                like_count = metrics["like_count"]

                if self._should_flush_metrics(online_count=online_count, like_count=like_count):
                    self._flush_to_db(
                        online_count=online_count,
                        like_count=like_count,
                    )

                # 抖音弹幕刷新很快，阈值设置得更小一些，尽快批量落库。
                if len(self.danmaku_buffer) >= 10:
                    self._flush_to_db(
                        online_count=online_count,
                        like_count=like_count,
                    )
            except Exception as exc:
                print(f"[{self.platform}] 抓取循环异常: {exc}")

            await asyncio.sleep(2)

        if self.danmaku_buffer:
            self._flush_to_db(online_count=0, like_count=0)
        await self.stop()

    async def _extract_messages(self) -> List[Dict[str, str]]:
        raw_messages = await self.page.evaluate(
            """
            () => {
              const itemSelectors = [
                '[data-e2e="chat-message-item"]',
                '.webcast-chatroom___item',
                '.chatroom-item',
                '[class*="chatroom"] [class*="item"]'
              ];
              const userSelectors = [
                '[data-e2e="message-author-name"]',
                '.webcast-chatroom___user-name',
                '.author-name',
                '[class*="user-name"]',
                '[class*="author"]'
              ];
              const contentSelectors = [
                '[data-e2e="message-content"]',
                '.webcast-chatroom___content',
                '.webcast-chatroom___content-with-emoji-text',
                '[class*="content"]'
              ];

              const findNodes = (selectors) => {
                for (const selector of selectors) {
                  const nodes = Array.from(document.querySelectorAll(selector));
                  if (nodes.length) return nodes;
                }
                return [];
              };

              const findText = (root, selectors) => {
                for (const selector of selectors) {
                  const node = root.querySelector(selector);
                  const text = node?.textContent?.trim();
                  if (text) return text;
                }
                return '';
              };

              return findNodes(itemSelectors)
                .slice(-30)
                .map((item) => {
                  const userName = findText(item, userSelectors);
                  const content = findText(item, contentSelectors) || item.textContent?.trim() || '';
                  return { user_name: userName, content, raw_text: item.textContent?.trim() || '' };
                })
                .filter((item) => item.content);
            }
            """
        )

        messages: List[Dict[str, str]] = []
        for item in raw_messages:
            user_name = (item.get("user_name") or "").strip()
            content = (item.get("content") or "").strip()
            raw_text = (item.get("raw_text") or "").strip()
            if not user_name and raw_text:
                parsed_user_name, parsed_content = self._split_chat_text(raw_text)
                user_name = parsed_user_name
                if parsed_content and (not content or content == raw_text):
                    content = parsed_content

            user_name = user_name or "anonymous"
            if not content:
                continue

            msg_hash = f"{user_name}::{content}"
            if msg_hash in self.last_msg_texts:
                continue

            self.last_msg_texts.add(msg_hash)
            messages.append({"user_name": user_name, "content": content})

        if len(self.last_msg_texts) > 2000:
            self.last_msg_texts.clear()

        return messages

    async def _extract_metrics(self) -> Dict[str, int]:
        values = await self.page.evaluate(
            """
            () => {
              const onlineSelectors = [
                '[data-e2e="room-user-count"]',
                '[data-e2e="live-people-count"]',
                '[class*="user-count"]',
                '[class*="audience-count"]',
                '[class*="room-viewer"]'
              ];
              const likeSelectors = [
                '[data-e2e="like-count"]',
                '[class*="like-count"]',
                '[class*="digg-count"]'
              ];

              const pickText = (selectors) => {
                for (const selector of selectors) {
                  const node = document.querySelector(selector);
                  const text = node?.textContent?.trim();
                  if (text) return text;
                }
                return '';
              };

              return {
                online_text: pickText(onlineSelectors),
                like_text: pickText(likeSelectors)
              };
            }
            """
        )

        if not values.get("online_text") or not values.get("like_text"):
            body_text = await self.page.evaluate(
                """
                () => (document.body?.innerText || '').replace(/\\s+/g, ' ').trim()
                """
            )
            fallback_values = self._extract_metrics_from_body_text(body_text)
            values["online_text"] = values.get("online_text") or fallback_values["online_text"]
            values["like_text"] = values.get("like_text") or fallback_values["like_text"]

        return {
            "online_count": self._parse_count(values.get("online_text", "")),
            "like_count": self._parse_count(values.get("like_text", "")),
        }

    def _flush_to_db(self, online_count: int, like_count: int):
        try:
            self.flush_danmaku_records(
                danmakus=self.danmaku_buffer,
                online_count=online_count,
                like_count=like_count,
            )
            print(
                f"[{self.platform}] 成功写入 {len(self.danmaku_buffer)} 条消息，"
                f"在线人数: {online_count}，点赞数: {like_count}"
            )
            self.danmaku_buffer.clear()
        except Exception as exc:
            print(f"[{self.platform}] 落库失败: {exc}")

    def _should_flush_metrics(self, online_count: int, like_count: int) -> bool:
        if self.danmaku_buffer:
            return False
        if online_count <= 0 and like_count <= 0:
            return False

        now = time.monotonic()
        if now - self.last_metric_flush_at < self.metric_flush_interval_seconds:
            return False

        self.last_metric_flush_at = now
        return True

    def _extract_metrics_from_body_text(self, body_text: str) -> Dict[str, str]:
        compact_text = body_text.replace(" ", "")

        online_text = self._match_first(
            compact_text,
            [
                r"在线观众[·:：]?(?P<count>\d+(?:\.\d+)?[万亿]?)",
                r"观众[·:：]?(?P<count>\d+(?:\.\d+)?[万亿]?)",
            ],
        )
        like_text = self._match_first(
            compact_text,
            [
                r"(?P<count>\d+(?:\.\d+)?[万亿]?)本场点赞",
                r"本场点赞[·:：]?(?P<count>\d+(?:\.\d+)?[万亿]?)",
            ],
        )
        return {
            "online_text": online_text,
            "like_text": like_text,
        }

    @staticmethod
    def _match_first(text: str, patterns: List[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group("count")
        return ""

    @staticmethod
    def _split_chat_text(raw_text: str) -> tuple[str, str]:
        compact = " ".join(raw_text.split()).strip()
        for separator in ("：", ":"):
            if separator not in compact:
                continue

            user_name, content = compact.split(separator, 1)
            user_name = user_name.strip()
            content = content.strip()
            if user_name and content:
                return user_name, content

        return "", ""

    @staticmethod
    def _parse_count(raw_text: str) -> int:
        text = raw_text.replace(",", "").replace(" ", "").strip()
        if not text:
            return 0

        multiplier = 1
        if "亿" in text:
            multiplier = 100000000
            text = text.replace("亿", "")
        elif "万" in text:
            multiplier = 10000
            text = text.replace("万", "")

        numeric = "".join(ch for ch in text if ch.isdigit() or ch == ".")
        if not numeric:
            return 0

        return int(float(numeric) * multiplier)
