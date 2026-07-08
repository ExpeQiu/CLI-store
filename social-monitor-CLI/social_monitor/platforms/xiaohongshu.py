from typing import Any, Dict, List, Optional

from social_monitor.platforms.base import BaseCollector
from social_monitor.utils.cookie_manager import has_browser_session
from social_monitor.utils.rate_limiter import RateLimiter


class XiaoHongShuCollector(BaseCollector):
    """小红书采集器（优先 Playwright 浏览器签名，备选 httpx + Cookie）"""

    platform_name = "xiaohongshu"
    API_BASE = "https://edith.xiaohongshu.com/api/sns/web/v1"
    WEB_BASE = "https://edith.xiaohongshu.com/api/sns/web/v2"

    def __init__(self, cookie: Optional[str] = None, use_browser: Optional[bool] = None, safe_mode: bool = False):
        super().__init__(cookie=cookie, safe_mode=safe_mode)
        if not safe_mode:
            self.rate_limiter = RateLimiter(min_interval=5.0, max_interval=10.0)
        # auto: 有 browser session 则用浏览器
        if use_browser is None:
            self.use_browser = has_browser_session("xiaohongshu")
        else:
            self.use_browser = use_browser

    def _fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> dict:
        if self.use_browser:
            from social_monitor.utils.browser import browser_fetch_json

            self.logger.info("使用 Playwright 浏览器采集（自动签名）")
            return browser_fetch_json("xiaohongshu", url, params=params)

        if not self.cookie:
            self.logger.error("无浏览器登录态且未配置 Cookie")
            return {"success": False, "msg": "需要 config login xiaohongshu 或配置 Cookie"}

        self.logger.info("使用 httpx + Cookie 采集（部分接口可能因签名失败）")
        headers = {
            "Cookie": self.cookie,
            "Referer": "https://www.xiaohongshu.com/",
            "Origin": "https://www.xiaohongshu.com",
        }
        resp = self.http_client.get(url, headers=headers, params=params)
        return resp.json()

    def fetch_user_notes(self, user_id: str, num: int = 20) -> List[Dict[str, Any]]:
        """获取用户笔记列表"""
        if not self.use_browser and not self.cookie:
            self.logger.error("小红书采集需要 Cookie 或 browser login")
            return []

        self.logger.info("采集小红书用户 user_id=%s mode=%s", user_id, "browser" if self.use_browser else "cookie")
        self.rate_limiter.wait()

        url = f"{self.WEB_BASE}/user_posted"
        params = {"user_id": user_id, "cursor": "", "num": num}

        try:
            data = self._fetch_json(url, params=params)
        except Exception as e:
            self.logger.error("小红书请求失败: %s", e)
            return []

        if not data.get("success", False):
            self.logger.error("小红书 API 返回失败: %s", data.get("msg", ""))
            return []

        notes = []
        for note in data.get("data", {}).get("notes", []):
            interact = note.get("interact_info", {})
            notes.append(
                {
                    "id": note.get("note_id", ""),
                    "note_id": note.get("note_id", ""),
                    "title": note.get("display_title", note.get("title", "")),
                    "type": note.get("type", ""),
                    "liked_count": interact.get("liked_count", 0),
                    "collected_count": interact.get("collected_count", 0),
                    "comment_count": interact.get("comment_count", 0),
                    "share_count": interact.get("share_count", 0),
                    "publish_time": note.get("time", 0),
                    "cover_url": note.get("cover", {}).get("url_default", ""),
                }
            )

        self.logger.info("获取笔记 %d 条", len(notes))
        return notes

    def search_notes(self, keyword: str, num: int = 20) -> List[Dict[str, Any]]:
        """按关键词搜索笔记"""
        if not self.use_browser and not self.cookie:
            self.logger.error("小红书搜索需要 Cookie 或 browser login")
            return []

        self.logger.info("搜索小红书主题 keyword=%s", keyword)
        self.rate_limiter.wait()
        url = f"{self.API_BASE}/search/notes"
        params = {"keyword": keyword, "page": 1, "page_size": num, "search_id": ""}

        try:
            data = self._fetch_json(url, params=params)
        except Exception as e:
            self.logger.error("小红书搜索失败: %s", e)
            return []

        items = data.get("data", {}).get("items") or data.get("data", {}).get("notes") or []
        notes = []
        for item in items:
            note = item.get("note_card") or item.get("note") or item
            interact = note.get("interact_info") or {}
            note_id = note.get("note_id") or note.get("id", "")
            notes.append(
                {
                    "id": note_id,
                    "note_id": note_id,
                    "title": note.get("display_title") or note.get("title", ""),
                    "keyword": keyword,
                    "liked_count": interact.get("liked_count", 0),
                    "comment_count": interact.get("comment_count", 0),
                    "type": note.get("type", ""),
                }
            )
        self.logger.info("搜索到笔记 %d 条", len(notes))
        return notes

    def fetch_note_comments(self, note_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取笔记评论"""
        if not self.use_browser and not self.cookie:
            self.logger.error("小红书评论需要 Cookie 或 browser login")
            return []

        self.rate_limiter.wait()
        url = f"{self.WEB_BASE}/comment/page"
        params = {"note_id": note_id, "cursor": "", "top_comment_id": "", "num": limit}
        self.logger.info("采集小红书评论 note_id=%s", note_id)

        try:
            data = self._fetch_json(url, params=params)
        except Exception as e:
            self.logger.error("小红书评论失败: %s", e)
            return []

        if not data.get("success", True) and data.get("code") not in (0, None):
            self.logger.error("小红书评论 API 失败: %s", data.get("msg", ""))
            return []

        comments = []
        for c in data.get("data", {}).get("comments") or []:
            comments.append(
                {
                    "id": c.get("id", ""),
                    "content": c.get("content", ""),
                    "user": c.get("user_info", {}).get("nickname", ""),
                    "like_count": c.get("like_count", 0),
                    "create_time": c.get("create_time", 0),
                }
            )
        self.logger.info("获取评论 %d 条", len(comments))
        return comments

    def fetch_note_detail(self, note_id: str) -> Dict[str, Any]:
        """获取笔记详情"""
        if not self.use_browser and not self.cookie:
            self.logger.error("小红书采集需要 Cookie 或 browser login")
            return {}

        self.rate_limiter.wait()
        url = f"{self.API_BASE}/feed"
        params = {"source_note_id": note_id}

        try:
            data = self._fetch_json(url, params=params)
        except Exception as e:
            self.logger.error("小红书请求失败: %s", e)
            return {}

        items = data.get("data", {}).get("items", [])
        if not items:
            return {}

        note = items[0].get("note_card", {})
        interact = note.get("interact_info", {})
        return {
            "id": note_id,
            "title": note.get("title", ""),
            "desc": note.get("desc", ""),
            "liked_count": interact.get("liked_count", 0),
            "images": [img.get("url_default", "") for img in note.get("image_list", [])],
        }

    def search_users(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """按昵称搜索小红书用户"""
        if not self.use_browser and not self.cookie:
            self.logger.error("小红书用户搜索需要 Cookie 或 browser login")
            return []

        self.logger.info("搜索小红书用户 keyword=%s", keyword)
        self.rate_limiter.wait()
        url = f"{self.API_BASE}/search/userinfo"
        params = {"keyword": keyword, "page": 1, "page_size": limit, "search_id": ""}

        try:
            data = self._fetch_json(url, params=params)
        except Exception as e:
            self.logger.error("小红书用户搜索失败: %s", e)
            return []

        items = data.get("data", {}).get("users") or data.get("data", {}).get("items") or []
        results = []
        for item in items:
            user = item.get("user") or item
            user_id = user.get("user_id") or user.get("id")
            if not user_id:
                continue
            results.append(
                {
                    "account_id": str(user_id),
                    "name": user.get("nickname") or user.get("name", ""),
                    "sign": user.get("desc") or user.get("signature", ""),
                    "profile_url": f"https://www.xiaohongshu.com/user/profile/{user_id}",
                    "fans": user.get("fans") or user.get("fans_count", 0),
                }
            )
        self.logger.info("小红书搜索到用户 %d 个", len(results))
        return results[:limit]

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self.fetch_user_notes(account_id)
