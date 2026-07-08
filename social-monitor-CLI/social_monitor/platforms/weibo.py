import random
import re
import time
from html import unescape
from typing import Any, Dict, List, Optional

from social_monitor.platforms.base import BaseCollector


class WeiboCollector(BaseCollector):
    """微博采集器"""

    platform_name = "weibo"
    BASE_URL = "https://m.weibo.cn/api/container/getIndex"
    HOT_SEARCH_URL = "https://weibo.com/ajax/side/hotSearch"

    def __init__(self, cookie: Optional[str] = None):
        super().__init__(cookie=cookie)

    def fetch_user_timeline(self, uid: str, max_page: int = 10) -> List[Dict[str, Any]]:
        """获取用户最新微博"""
        self.logger.info("采集微博用户 uid=%s pages=%d", uid, max_page)
        cards: List[Dict[str, Any]] = []

        for page in range(1, max_page + 1):
            params = {
                "uid": uid,
                "type": "uid",
                "value": uid,
                "containerid": f"107603{uid}",
                "page": page,
            }
            try:
                resp = self.http_client.get(self.BASE_URL, params=params)
                data = resp.json()
                page_cards = data.get("data", {}).get("cards", [])
                if not page_cards:
                    self.logger.info("第 %d 页无数据，停止分页", page)
                    break
                cards.extend(page_cards)
                self.logger.debug("第 %d 页获取 %d 条卡片", page, len(page_cards))
            except Exception as e:
                self.logger.error("第 %d 页请求失败: %s", page, e)
                break

            if page < max_page:
                time.sleep(random.uniform(2, 3))

        return self._parse_cards(cards)

    def fetch_trending(self, max_count: int = 50) -> List[Dict[str, Any]]:
        """获取微博热搜"""
        self.logger.info("采集微博热搜 count=%d", max_count)
        headers = {
            "Referer": "https://s.weibo.com/top/summary",
            "Accept": "application/json",
        }

        try:
            resp = self.http_client.get(self.HOT_SEARCH_URL, headers=headers)
            data = resp.json()
            items = data.get("data", {}).get("realtime", [])
        except Exception as e:
            self.logger.warning("hotSearch 接口失败，尝试 hot_band: %s", e)
            resp = self.http_client.get(
                "https://weibo.com/ajax/statuses/hot_band", headers=headers
            )
            data = resp.json()
            items = data.get("data", {}).get("band_list", [])

        trending = []
        for item in items:
            trending.append(
                {
                    "rank": item.get("rank", item.get("pos", len(trending) + 1)),
                    "word": item.get("word", item.get("note", "")),
                    "hot_value": item.get("num", item.get("raw_hot", 0)),
                    "label": item.get("label_name", item.get("flag_desc", "")),
                }
            )

        return trending[:max_count]

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        max_page = kwargs.get("max_page", 5)
        return self.fetch_user_timeline(account_id, max_page=max_page)

    def _parse_cards(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析微博卡片数据"""
        results = []
        for card in cards:
            mblog = card.get("mblog")
            if not mblog:
                continue

            user = mblog.get("user", {})
            text = mblog.get("text", "")
            text = re.sub(r"<[^>]+>", "", text)
            text = unescape(text)

            results.append(
                {
                    "id": str(mblog.get("id", "")),
                    "text": text,
                    "created_at": mblog.get("created_at", ""),
                    "reposts_count": mblog.get("reposts_count", 0),
                    "comments_count": mblog.get("comments_count", 0),
                    "attitudes_count": mblog.get("attitudes_count", 0),
                    "screen_name": user.get("screen_name", ""),
                    "followers_count": user.get("followers_count", 0),
                    "source": mblog.get("source", ""),
                }
            )

        self.logger.info("解析完成，共 %d 条微博", len(results))
        return results
