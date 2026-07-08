import asyncio
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Union

from social_monitor.platforms.base import BaseCollector
from social_monitor.utils.bilibili_live import (
    LIVE_WS_URL,
    build_auth_packet,
    build_heartbeat_packet,
    parse_live_messages,
)
from social_monitor.utils.bilibili_wbi import BilibiliWbiSigner
from social_monitor.utils.danmaku_words import extract_danmaku_words


class BilibiliCollector(BaseCollector):
    """B站采集器"""

    platform_name = "bilibili"
    API_BASE = "https://api.bilibili.com"
    LIVE_API_BASE = "https://api.live.bilibili.com"

    def __init__(
        self,
        cookie: Optional[str] = None,
        headers: Optional[dict] = None,
        safe_mode: bool = False,
    ):
        super().__init__(cookie=cookie, headers=headers, safe_mode=safe_mode)
        self._wbi_signer = BilibiliWbiSigner(self.http_client)

    def fetch_user_videos(self, uid: int, page: int = 1, page_size: int = 30) -> List[Dict[str, Any]]:
        """获取 UP 主视频列表（优先 WBI，失败时回退 arc/list）"""
        self.logger.info("采集B站 UP 主 uid=%s", uid)
        headers = {"Referer": f"https://space.bilibili.com/{uid}/video"}
        params = {
            "mid": uid,
            "ps": page_size,
            "pn": page,
            "order": "pubdate",
            "platform": "web",
        }

        data = self._request_wbi_json(
            f"{self.API_BASE}/x/space/wbi/arc/search",
            params,
            headers=headers,
        )
        if data:
            items = data.get("data", {}).get("list", {}).get("vlist", [])
            videos = [self._parse_vlist_item(item) for item in items]
            self.logger.info("获取视频 %d 条 (WBI)", len(videos))
            return videos

        self.logger.info("WBI 接口不可用，回退 arc/list uid=%s", uid)
        return self._fetch_user_videos_arc_list(uid, page, page_size, headers)

    @staticmethod
    def _format_duration(value: Any) -> str:
        if isinstance(value, str):
            return value
        seconds = int(value or 0)
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    def _parse_vlist_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("bvid", ""),
            "bvid": item.get("bvid", ""),
            "title": item.get("title", ""),
            "desc": item.get("description", ""),
            "pic": item.get("pic", ""),
            "duration": item.get("length", "") or self._format_duration(item.get("duration")),
            "view": item.get("play", 0),
            "comment": item.get("comment", 0),
            "publish_time": item.get("created", 0),
        }

    def _parse_archive_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        stat = item.get("stat", {})
        return {
            "id": item.get("bvid", ""),
            "bvid": item.get("bvid", ""),
            "title": item.get("title", ""),
            "desc": item.get("desc", ""),
            "pic": item.get("pic", ""),
            "duration": self._format_duration(item.get("duration")),
            "view": stat.get("view", 0),
            "comment": stat.get("reply", 0),
            "publish_time": item.get("pubdate", 0),
        }

    def _fetch_user_videos_arc_list(
        self,
        uid: int,
        page: int,
        page_size: int,
        headers: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        url = f"{self.API_BASE}/x/space/arc/list"
        params = {"mid": uid, "ps": page_size, "pn": page}
        self._wbi_signer._warmup_cookies()
        resp = self.http_client.get(url, params=params, headers=headers)
        data = resp.json()
        if data.get("code") != 0:
            self.logger.error("B站 arc/list 错误: %s", data.get("message", ""))
            return []
        items = data.get("data", {}).get("archives", [])
        videos = [self._parse_archive_item(item) for item in items]
        self.logger.info("获取视频 %d 条 (arc/list)", len(videos))
        return videos

    def _request_wbi_json(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """带 WBI 签名的 JSON 请求，失败时重试一次（刷新 key）"""
        import httpx

        for attempt in range(2):
            signed = self._wbi_signer.sign(params, force_refresh=attempt > 0)
            try:
                resp = self.http_client.get(url, params=signed, headers=headers)
            except httpx.HTTPStatusError as e:
                self.logger.warning("B站 WBI HTTP 错误: %s", e)
                continue

            data = resp.json()
            code = data.get("code")
            if code == 0:
                return data
            message = data.get("message", "")
            self.logger.warning("B站 WBI API 错误: %s (code=%s)", message, code)
            if attempt == 0 and code in (-403, -352):
                self.logger.info("WBI 签名可能过期或被风控，刷新 key 后重试")
                continue
            return None
        return None

    def fetch_trending(self, rid: int = 0) -> List[Dict[str, Any]]:
        """获取排行榜"""
        self.logger.info("采集B站排行榜 rid=%d", rid)
        url = f"{self.API_BASE}/x/web-interface/ranking/v2"
        params = {"rid": rid, "type": "all"}

        resp = self.http_client.get(url, params=params)
        data = resp.json()

        ranking = []
        for item in data.get("data", {}).get("list", []):
            stat = item.get("stat", {})
            ranking.append(
                {
                    "rank": len(ranking) + 1,
                    "bvid": item.get("bvid", ""),
                    "title": item.get("title", ""),
                    "owner": item.get("owner", {}).get("name", ""),
                    "view": stat.get("view", 0),
                    "like": stat.get("like", 0),
                    "reply": stat.get("reply", 0),
                }
            )

        return ranking

    def resolve_video_cid(self, bvid: Optional[str] = None, aid: Optional[int] = None) -> Dict[str, Any]:
        """通过 bvid 或 aid 获取视频 cid"""
        if not bvid and not aid:
            raise ValueError("需要 bvid 或 aid")

        params: Dict[str, Union[str, int]] = {}
        if bvid:
            params["bvid"] = bvid
        else:
            params["aid"] = aid

        url = f"{self.API_BASE}/x/web-interface/view"
        resp = self.http_client.get(url, params=params)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"B站视频信息获取失败: {data.get('message', '')}")

        video = data.get("data", {})
        pages = video.get("pages") or []
        if not pages:
            raise RuntimeError("视频无分 P 信息")

        return {
            "aid": video.get("aid", 0),
            "bvid": video.get("bvid", ""),
            "cid": pages[0].get("cid", 0),
            "title": video.get("title", ""),
        }

    def fetch_video_stat(
        self,
        bvid: Optional[str] = None,
        aid: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取视频完整互动数据"""
        params: Dict[str, Union[str, int]] = {}
        if bvid:
            params["bvid"] = bvid
        elif aid:
            params["aid"] = aid
        else:
            raise ValueError("需要 bvid 或 aid")

        url = f"{self.API_BASE}/x/web-interface/view"
        resp = self.http_client.get(url, params=params)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"B站视频 stat 失败: {data.get('message', '')}")

        video = data.get("data", {})
        stat = video.get("stat", {})
        self.logger.info("采集B站视频 stat bvid=%s", video.get("bvid", ""))
        return {
            "id": video.get("bvid", ""),
            "bvid": video.get("bvid", ""),
            "aid": video.get("aid", 0),
            "title": video.get("title", ""),
            "view": stat.get("view", 0),
            "like": stat.get("like", 0),
            "coin": stat.get("coin", 0),
            "favorite": stat.get("favorite", 0),
            "share": stat.get("share", 0),
            "reply": stat.get("reply", 0),
            "danmaku": stat.get("danmaku", 0),
        }

    def fetch_video_danmaku(
        self,
        bvid: Optional[str] = None,
        aid: Optional[int] = None,
        cid: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取视频弹幕（XML 接口）"""
        if cid is None:
            meta = self.resolve_video_cid(bvid=bvid, aid=aid)
            cid = meta["cid"]
            bvid = meta.get("bvid") or bvid
            aid = meta.get("aid") or aid

        self.logger.info("采集B站视频弹幕 cid=%s bvid=%s", cid, bvid)
        url = f"https://comment.bilibili.com/{cid}.xml"
        resp = self.http_client.get(url, headers={"Accept": "application/xml, text/xml, */*"})
        root = ET.fromstring(resp.text)

        danmaku: List[Dict[str, Any]] = []
        for node in root.findall("d"):
            content = (node.text or "").strip()
            if not content:
                continue
            attrs = (node.get("p") or "").split(",")
            danmaku.append(
                {
                    "content": content,
                    "time": float(attrs[0]) if attrs else 0.0,
                    "mode": int(attrs[1]) if len(attrs) > 1 else 0,
                    "color": int(attrs[3]) if len(attrs) > 3 else 0,
                    "timestamp": int(attrs[4]) if len(attrs) > 4 else 0,
                    "cid": cid,
                    "bvid": bvid or "",
                    "aid": aid or 0,
                    "platform": "bilibili_video",
                }
            )
            if limit and len(danmaku) >= limit:
                break

        self.logger.info("获取视频弹幕 %d 条", len(danmaku))
        return danmaku

    def fetch_danmaku_words(
        self,
        bvid: Optional[str] = None,
        aid: Optional[int] = None,
        cid: Optional[int] = None,
        top_n: int = 50,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """采集视频弹幕并统计高频词"""
        danmaku = self.fetch_video_danmaku(bvid=bvid, aid=aid, cid=cid, limit=limit)
        words = extract_danmaku_words(danmaku, top_n=top_n)
        self.logger.info("提取弹幕高频词 %d 个", len(words))
        return words

    def resolve_live_room_id(self, room_id: int) -> int:
        """解析直播间真实 room_id（短号转长号）"""
        url = f"{self.LIVE_API_BASE}/room/v1/Room/room_init"
        resp = self.http_client.get(url, params={"id": room_id})
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"直播间信息获取失败: {data.get('message', '')}")
        real_room_id = data.get("data", {}).get("room_id", room_id)
        self.logger.info("直播间 room_id=%s -> real_room_id=%s", room_id, real_room_id)
        return int(real_room_id)

    def fetch_live_room_info(self, room_id: int) -> Dict[str, Any]:
        """获取直播间基础信息"""
        real_room_id = self.resolve_live_room_id(room_id)
        url = f"{self.LIVE_API_BASE}/room/v1/Room/get_info"
        resp = self.http_client.get(url, params={"room_id": real_room_id})
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"直播间详情获取失败: {data.get('message', '')}")
        info = data.get("data", {})
        return {
            "room_id": real_room_id,
            "short_id": info.get("short_id", 0),
            "title": info.get("title", ""),
            "uname": info.get("uname", ""),
            "live_status": info.get("live_status", 0),
            "online": info.get("online", 0),
        }

    def fetch_live_danmaku(
        self,
        room_id: int,
        duration: int = 60,
        max_count: int = 200,
        include_interact: bool = False,
    ) -> List[Dict[str, Any]]:
        """采集直播间实时弹幕（WebSocket）"""
        try:
            import websockets
        except ImportError as e:
            raise RuntimeError(
                "直播弹幕需要 websockets，请安装: pip install 'social-monitor[live]'"
            ) from e

        room_info = self.fetch_live_room_info(room_id)
        real_room_id = room_info["room_id"]
        if room_info.get("live_status") != 1:
            self.logger.warning(
                "直播间未开播 room_id=%s title=%s，跳过弹幕采集",
                real_room_id,
                room_info.get("title"),
            )
            return []

        self.logger.info(
            "开始采集直播弹幕 room_id=%s duration=%ss max_count=%s",
            real_room_id,
            duration,
            max_count,
        )
        return asyncio.run(
            self._collect_live_danmaku(
                websockets,
                real_room_id,
                duration=duration,
                max_count=max_count,
                include_interact=include_interact,
            )
        )

    async def _collect_live_danmaku(
        self,
        websockets,
        room_id: int,
        duration: int,
        max_count: int,
        include_interact: bool,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        deadline = time.time() + max(duration, 1)

        try:
            async with websockets.connect(LIVE_WS_URL, ping_interval=None, proxy=None) as ws:
                await ws.send(build_auth_packet(room_id))
                self.logger.debug("直播弹幕鉴权包已发送 room_id=%s", room_id)

                while time.time() < deadline and len(collected) < max_count:
                    timeout = min(5.0, max(0.1, deadline - time.time()))
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        await ws.send(build_heartbeat_packet())
                        continue

                    for msg in parse_live_messages(raw):
                        if not include_interact and msg.get("content", "").startswith("["):
                            continue
                        collected.append(msg)
                        if len(collected) >= max_count:
                            break

                    if time.time() + 25 < deadline:
                        await ws.send(build_heartbeat_packet())
        except Exception as e:
            self.logger.warning("直播弹幕 WebSocket 异常: %s（已采集 %d 条）", e, len(collected))

        self.logger.info("直播弹幕采集完成 %d 条", len(collected))
        return collected

    def fetch_live_danmaku_words(
        self,
        room_id: int,
        duration: int = 60,
        max_count: int = 200,
        top_n: int = 50,
    ) -> List[Dict[str, Any]]:
        """采集直播弹幕并统计高频词"""
        danmaku = self.fetch_live_danmaku(room_id, duration=duration, max_count=max_count)
        words = extract_danmaku_words(danmaku, top_n=top_n)
        self.logger.info("提取直播弹幕高频词 %d 个", len(words))
        return words

    def fetch_hot_comments(self, aid: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取视频热门评论"""
        self.logger.info("采集B站评论 aid=%d", aid)
        url = f"{self.API_BASE}/x/v2/reply/main"
        params = {"type": 1, "oid": aid, "mode": 3, "ps": limit}

        resp = self.http_client.get(url, params=params)
        data = resp.json()

        replies = []
        for reply in data.get("data", {}).get("replies") or []:
            replies.append(
                {
                    "id": str(reply.get("rpid", "")),
                    "uname": reply.get("member", {}).get("uname", ""),
                    "content": reply.get("content", {}).get("message", ""),
                    "like": reply.get("like", 0),
                    "ctime": reply.get("ctime", 0),
                }
            )

        return replies

    def fetch_danmaku(self, aid: int, limit: int = 10) -> List[Dict[str, Any]]:
        """兼容旧接口：获取热门评论（非弹幕）"""
        return self.fetch_hot_comments(aid, limit=limit)

    def search_users(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """按昵称搜索 UP 主，返回 mid / name / sign"""
        self.logger.info("搜索 B站用户 keyword=%s", keyword)
        headers = {"Referer": "https://search.bilibili.com/"}
        params = {
            "search_type": "bili_user",
            "keyword": keyword,
            "page": 1,
            "page_size": limit,
            "order": "totalrank",
        }
        url = f"{self.API_BASE}/x/web-interface/wbi/search/type"
        data = self._request_wbi_json(url, params, headers=headers)
        if not data:
            url = f"{self.API_BASE}/x/web-interface/search/type"
            try:
                resp = self.http_client.get(url, params=params, headers=headers)
                data = resp.json()
            except Exception as e:
                self.logger.error("B站用户搜索失败: %s", e)
                return []
            if data.get("code") != 0:
                self.logger.error("B站用户搜索 API 错误: %s", data.get("message", ""))
                return []

        results = []
        for item in data.get("data", {}).get("result", []) or []:
            mid = item.get("mid")
            if not mid:
                continue
            results.append(
                {
                    "account_id": str(mid),
                    "name": item.get("uname") or item.get("title", ""),
                    "sign": item.get("usign") or item.get("sign", ""),
                    "profile_url": f"https://space.bilibili.com/{mid}",
                    "fans": item.get("fans", 0),
                }
            )
        self.logger.info("B站搜索到用户 %d 个", len(results))
        return results

    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self.fetch_user_videos(int(account_id))
