import re
from html import unescape
from typing import Any, Dict, List, Optional

from social_monitor.platforms.base import BaseCollector


class ZhihuCollector(BaseCollector):
    """知乎采集器"""

    platform_name = "zhihu"
    API_BASE = "https://www.zhihu.com/api/v4"
    HOT_LIST_URL = "https://api.zhihu.com/topstory/hot-lists/total"
    HOT_RANK_URL = f"{API_BASE}/creators/rank/hot"

    def __init__(self, cookie: Optional[str] = None):
        super().__init__(
            cookie=cookie,
            headers={
                "X-API-VERSION": "3.0.40",
                "Referer": "https://www.zhihu.com/hot",
            },
        )

    def fetch_trending(self, max_count: int = 20) -> List[Dict[str, Any]]:
        """获取知乎热榜"""
        self.logger.info("采集知乎热榜 count=%d", max_count)

        try:
            resp = self.http_client.get(self.HOT_LIST_URL, params={"limit": max_count})
            data = resp.json()
            items = data.get("data", [])
            if items:
                return self._parse_hot_list(items, max_count)
        except Exception as e:
            self.logger.warning("主热榜接口失败，尝试备用: %s", e)

        resp = self.http_client.get(self.HOT_RANK_URL, params={"domain": 0, "limit": max_count})
        data = resp.json()
        return self._parse_creator_rank(data.get("data", []), max_count)

    def _parse_hot_list(self, items: List[Dict[str, Any]], max_count: int) -> List[Dict[str, Any]]:
        trending = []
        for item in items:
            target = item.get("target", {})
            title = target.get("title", "")
            if not title:
                continue
            trending.append(
                {
                    "rank": len(trending) + 1,
                    "id": str(target.get("id", item.get("card_id", ""))),
                    "type": target.get("type", ""),
                    "title": title,
                    "excerpt": target.get("excerpt", ""),
                    "answer_count": target.get("answer_count", 0),
                    "follower_count": target.get("follower_count", 0),
                    "url": self._to_web_url(target),
                    "hot_value": item.get("detail_text", ""),
                    "label": item.get("card_label", {}).get("type", ""),
                }
            )
        self.logger.info("获取热榜 %d 条", len(trending))
        return trending[:max_count]

    def _parse_creator_rank(self, items: List[Dict[str, Any]], max_count: int) -> List[Dict[str, Any]]:
        trending = []
        for item in items:
            question = item.get("question", {})
            reaction = item.get("reaction", {})
            title = question.get("title", "")
            if not title:
                continue
            trending.append(
                {
                    "rank": len(trending) + 1,
                    "id": str(question.get("id", "")),
                    "type": "question",
                    "title": title,
                    "excerpt": "",
                    "answer_count": reaction.get("answer_num", 0),
                    "follower_count": reaction.get("follow_num", 0),
                    "url": question.get("url", ""),
                    "hot_value": reaction.get("new_pv", 0),
                    "label": question.get("label", ""),
                }
            )
        self.logger.info("获取创作者热榜 %d 条（备用源）", len(trending))
        return trending[:max_count]

    @staticmethod
    def _to_web_url(target: Dict[str, Any]) -> str:
        url = target.get("url", "")
        if url.startswith("https://api.zhihu.com/questions/"):
            qid = url.rsplit("/", 1)[-1]
            return f"https://www.zhihu.com/question/{qid}"
        return url

    def fetch_question_answers(
        self, question_id: str, max_count: int = 10
    ) -> List[Dict[str, Any]]:
        """获取问题的高赞回答"""
        self.logger.info("采集知乎问题 question_id=%s", question_id)
        url = f"{self.API_BASE}/questions/{question_id}/answers"
        params = {"sort_by": "default", "limit": 20, "offset": 0}

        headers = {}
        if self.cookie:
            headers["Cookie"] = self.cookie

        resp = self.http_client.get(url, params=params, headers=headers or None)
        data = resp.json()

        answers = []
        for item in data.get("data", [])[:max_count]:
            content = item.get("content", "")
            content = re.sub(r"<[^>]+>", "", content)
            content = unescape(content)

            answers.append(
                {
                    "id": str(item.get("id", "")),
                    "author": item.get("author", {}).get("name", ""),
                    "voteup_count": item.get("voteup_count", 0),
                    "content": content,
                    "created_time": item.get("created_time", 0),
                }
            )

        return answers

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        max_count = kwargs.get("max_count", 10)
        return self.fetch_question_answers(account_id, max_count=max_count)
