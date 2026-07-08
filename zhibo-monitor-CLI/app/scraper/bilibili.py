import asyncio
from typing import Dict, List

from app.scraper.base import BaseScraper

class BilibiliScraper(BaseScraper):
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
            platform="bilibili",
            event_name=event_name,
            car_brand=car_brand,
            car_model=car_model,
            event_id=event_id,
            headless=headless,
        )
        self.url = f"https://live.bilibili.com/{room_id}"
        self.danmaku_buffer: List[Dict] = []
        self.last_msg_texts = set()  # 简单去重池
        self.latest_online_count = 0

    async def start(self):
        await super().start()
        # 打开B站直播间
        await self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
        # 等待弹幕区域加载
        try:
            await self.page.wait_for_selector("#chat-history-list", timeout=10000)
            print(f"[{self.platform}] 成功进入直播间: {self.room_id}")
        except Exception as e:
            print(f"[{self.platform}] 进入直播间超时或页面结构变更: {e}")

    async def run_loop(self):
        """循环读取 DOM 中的弹幕并批量入库"""
        await self.start()

        while self.is_running:
            try:
                # 1. 解析弹幕
                # B站弹幕DOM结构: .chat-item.danmaku-item -> .user-name (用户名) 和 .danmaku-item-right (内容)
                chat_items = await self.page.query_selector_all("#chat-history-list .chat-item.danmaku-item")
                
                new_danmakus = []
                for item in chat_items:
                    try:
                        user_name_element = await item.query_selector(".user-name")
                        content_element = await item.query_selector(".danmaku-item-right")
                        
                        if user_name_element and content_element:
                            user_name = await user_name_element.inner_text()
                            content = await content_element.inner_text()
                            
                            # 简单防重: 根据用户名+内容拼接的哈希去重
                            msg_hash = f"{user_name}::{content}"
                            if msg_hash not in self.last_msg_texts:
                                self.last_msg_texts.add(msg_hash)
                                new_danmakus.append({
                                    "user_name": user_name.strip(),
                                    "content": content.strip()
                                })
                    except Exception as e:
                        continue
                
                # 维护去重池大小
                if len(self.last_msg_texts) > 1000:
                    self.last_msg_texts.clear()
                    
                if new_danmakus:
                    self.danmaku_buffer.extend(new_danmakus)
                    print(f"[{self.platform}] 抓取到 {len(new_danmakus)} 条新弹幕")

                # 2. 解析热度 (页面选择器优先，接口兜底)
                online_count = await self._get_online_count()

                self.latest_online_count = online_count

                # 3. 批量落库逻辑: 累计 20 条弹幕后写一次
                if len(self.danmaku_buffer) >= 20:
                    self._flush_to_db(online_count)

            except Exception as e:
                print(f"[{self.platform}] 抓取循环异常: {e}")
            
            # 每 2 秒抓取一次 DOM
            await asyncio.sleep(2)

        self._flush_to_db(current_online_count=self.latest_online_count)
        await self.stop()

    async def _get_online_count(self) -> int:
        """优先从页面读取热度，失败时退回到浏览器上下文接口请求。"""
        selector_candidates = [
            ".live-skin-popular-value",
        ]

        for selector in selector_candidates:
            try:
                hot_element = await self.page.query_selector(selector)
                if hot_element:
                    hot_text = await hot_element.inner_text()
                    count = self._parse_count_text(hot_text)
                    if count > 0:
                        return count
            except Exception:
                continue

        try:
            payload = await self.page.evaluate(
                """async (roomId) => {
                    const url = `https://api.live.bilibili.com/room/v1/Room/get_info?room_id=${roomId}`;
                    const res = await fetch(url, { credentials: 'include' });
                    return await res.json();
                }""",
                self.room_id,
            )
            if payload.get("code") == 0:
                return int(payload.get("data", {}).get("online") or 0)
        except Exception:
            pass

        return 0

    def _parse_count_text(self, text: str) -> int:
        cleaned = text.strip().replace(",", "")
        if not cleaned:
            return 0

        try:
            if "万" in cleaned:
                return int(float(cleaned.replace("万", "")) * 10000)
            return int(cleaned)
        except ValueError:
            return 0
            
    def _flush_to_db(self, current_online_count: int):
        """将缓冲区的弹幕写入数据库"""
        try:
            self.flush_danmaku_records(
                danmakus=self.danmaku_buffer,
                online_count=current_online_count,
                like_count=0,
            )
            print(f"[{self.platform}] 成功将 {len(self.danmaku_buffer)} 条弹幕写入数据库，当前热度: {current_online_count}")
            self.danmaku_buffer.clear()
        except Exception as e:
            print(f"[{self.platform}] 落库失败: {e}")
