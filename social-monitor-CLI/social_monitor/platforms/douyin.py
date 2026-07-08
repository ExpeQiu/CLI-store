from typing import Any, Dict, List, Optional

from social_monitor.platforms.base import BaseCollector


class DouYinCollector(BaseCollector):
    """抖音采集器"""

    platform_name = "douyin"
    HOT_SEARCH_URL = "https://aweme-hl.snssdk.com/aweme/v1/hot/search/list/"
    USER_VIDEOS_URL = "https://www.douyin.com/aweme/v1/web/aweme/post/"

    def fetch_trending(self, max_count: int = 50) -> List[Dict[str, Any]]:
        """获取抖音热榜"""
        self.logger.info("采集抖音热榜 count=%d", max_count)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            ),
        }

        resp = self.http_client.get(self.HOT_SEARCH_URL, headers=headers)
        data = resp.json()

        trending = []
        for item in data.get("data", {}).get("word_list", []):
            trending.append(
                {
                    "rank": item.get("position", item.get("rank", 0)),
                    "word": item.get("word", ""),
                    "hot_value": item.get("hot_value", 0),
                    "label": item.get("label", ""),
                    "event": item.get("event_time", ""),
                    "video_count": item.get("video_count", 0),
                    "discuss_count": item.get("discuss_video_count", 0),
                }
            )

        self.logger.info("获取热榜 %d 条", len(trending))
        return trending[:max_count]

    def fetch_user_videos(
        self, sec_uid: str, max_count: int = 20, cookie: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户视频列表（需 Cookie）"""
        use_cookie = cookie or self.cookie
        if not use_cookie:
            self.logger.warning("抖音用户视频采集需要 Cookie")
            return []

        self.logger.info("采集抖音用户 sec_uid=%s", sec_uid)
        headers = {"Cookie": use_cookie}
        params = {"sec_user_id": sec_uid, "count": max_count, "max_cursor": 0}

        resp = self.http_client.get(self.USER_VIDEOS_URL, headers=headers, params=params)
        data = resp.json()

        videos = []
        for item in data.get("aweme_list", []):
            stats = item.get("statistics", {})
            videos.append(
                {
                    "id": str(item.get("aweme_id", "")),
                    "desc": item.get("desc", ""),
                    "create_time": item.get("create_time", 0),
                    "digg_count": stats.get("digg_count", 0),
                    "comment_count": stats.get("comment_count", 0),
                    "share_count": stats.get("share_count", 0),
                    "play_count": stats.get("play_count", 0),
                }
            )

        return videos

    def fetch_video_comments(
        self,
        aweme_id: str,
        max_count: int = 20,
        cookie: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取视频评论（需 Cookie）"""
        use_cookie = cookie or self.cookie
        if not use_cookie:
            self.logger.warning("抖音评论采集需要 Cookie")
            return []

        self.logger.info("采集抖音评论 aweme_id=%s", aweme_id)
        url = "https://www.douyin.com/aweme/v1/web/comment/list/"
        headers = {
            "Cookie": use_cookie,
            "Referer": f"https://www.douyin.com/video/{aweme_id}",
        }
        params = {"aweme_id": aweme_id, "cursor": 0, "count": max_count}

        try:
            resp = self.http_client.get(url, headers=headers, params=params)
            data = resp.json()
        except Exception as e:
            self.logger.error("抖音评论请求失败: %s", e)
            return []

        comments = []
        for item in data.get("comments") or []:
            comments.append(
                {
                    "id": str(item.get("cid", "")),
                    "text": item.get("text", ""),
                    "user": item.get("user", {}).get("nickname", ""),
                    "digg_count": item.get("digg_count", 0),
                    "create_time": item.get("create_time", 0),
                }
            )
        self.logger.info("获取评论 %d 条", len(comments))
        return comments

    def search_users(self, keyword: str, limit: int = 5, cookie: Optional[str] = None) -> List[Dict[str, Any]]:
        """按昵称搜索抖音用户（需 Cookie）"""
        use_cookie = cookie or self.cookie
        if not use_cookie:
            self.logger.warning("抖音用户搜索需要 Cookie")
            return []

        self.logger.info("搜索抖音用户 keyword=%s", keyword)
        headers = {
            "Cookie": use_cookie,
            "Referer": "https://www.douyin.com/",
        }
        params = {
            "keyword": keyword,
            "search_source": "normal_search",
            "query_correct_type": "1",
            "offset": 0,
            "count": limit,
            "search_channel": "aweme_user_web",
        }
        url = "https://www.douyin.com/aweme/v1/web/discover/search/"

        try:
            resp = self.http_client.get(url, headers=headers, params=params)
            data = resp.json()
        except Exception as e:
            self.logger.error("抖音用户搜索失败: %s", e)
            return []

        results = []
        for block in data.get("user_list") or data.get("data") or []:
            user_info = block.get("user_info") or block
            sec_uid = user_info.get("sec_uid")
            if not sec_uid:
                continue
            unique_id = user_info.get("unique_id") or user_info.get("short_id") or ""
            results.append(
                {
                    "account_id": sec_uid,
                    "name": user_info.get("nickname", ""),
                    "unique_id": unique_id,
                    "sign": user_info.get("signature", ""),
                    "profile_url": f"https://www.douyin.com/user/{sec_uid}",
                    "follower_count": user_info.get("follower_count", 0),
                }
            )
        self.logger.info("抖音搜索到用户 %d 个", len(results))
        return results[:limit]

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self.fetch_user_videos(account_id, cookie=kwargs.get("cookie"))
