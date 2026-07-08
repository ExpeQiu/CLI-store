import re
from html import unescape
from typing import Any, Dict, List, Optional

import feedparser

from social_monitor.platforms.base import BaseCollector


class WeChatCollector(BaseCollector):
    """微信公众号采集器"""

    platform_name = "wechat"

    def __init__(
        self,
        rsshub_url: str = "http://localhost:1200",
        cookie: Optional[str] = None,
        safe_mode: bool = False,
    ):
        super().__init__(cookie=cookie, safe_mode=safe_mode)
        self.rsshub_url = rsshub_url.rstrip("/")

    def fetch_via_rsshub(self, wxid: str) -> List[Dict[str, Any]]:
        """通过 RSSHub 获取公众号文章"""
        routes = [
            ("profile", f"{self.rsshub_url}/wechat/mp/profile/{wxid}"),
            ("feed", f"{self.rsshub_url}/wechat/feed/{wxid}"),
        ]
        self.logger.info("采集微信公众号 wxid=%s via RSSHub", wxid)

        errors: List[str] = []
        for route_name, url in routes:
            try:
                resp = self.http_client.get(url)
                articles = self._parse_feed(resp.text)
                self.logger.info("获取文章 %d 篇 (route=%s)", len(articles), route_name)
                return articles
            except Exception as e:
                self.logger.error("RSSHub %s 路由失败 (%s): %s", route_name, url, e)
                errors.append(f"{route_name}: {e}")

        raise RuntimeError(
            f"RSSHub 不可用 ({self.rsshub_url})，主备路由均失败。"
            f"请检查服务是否运行或修改 rsshub_url。详情: {'; '.join(errors)}"
        )

    def _parse_feed(self, raw: str) -> List[Dict[str, Any]]:
        feed = feedparser.parse(raw)
        articles = []
        for entry in feed.entries:
            articles.append(
                {
                    "id": entry.get("id", entry.get("link", "")),
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "summary": self._clean_html(entry.get("summary", "")),
                    "publish_at": entry.get("published", ""),
                    "author": entry.get("author", ""),
                }
            )
        return articles

    def search_accounts(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """通过搜狗微信搜索公众号，解析 biz（wxid）"""
        self.logger.info("搜索微信公众号 keyword=%s", keyword)
        url = "https://weixin.sogou.com/weixin"
        params = {"type": 1, "query": keyword, "ie": "utf8"}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://weixin.sogou.com/",
        }

        try:
            resp = self.http_client.get(url, params=params, headers=headers)
            html = resp.text
        except Exception as e:
            self.logger.error("搜狗微信搜索失败: %s", e)
            return []

        results = []
        seen = set()
        # 账号块：昵称 + 链接中的 __biz=
        for block in re.findall(r'class="txt-box"[\s\S]*?</div>\s*</div>', html):
            name_match = re.search(r'<p[^>]*>\s*<a[^>]*>([^<]+)</a>', block)
            biz_match = re.search(r"__biz=([A-Za-z0-9_=+-]+)", block)
            if not name_match or not biz_match:
                continue
            biz = biz_match.group(1)
            if biz in seen:
                continue
            seen.add(biz)
            name = unescape(name_match.group(1).strip())
            results.append(
                {
                    "account_id": biz,
                    "name": name,
                    "profile_url": f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}",
                }
            )
            if len(results) >= limit:
                break

        self.logger.info("公众号搜索到 %d 个候选", len(results))
        return results

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self.fetch_via_rsshub(account_id)

    @staticmethod
    def _clean_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", "", html)
        return unescape(text).strip()
