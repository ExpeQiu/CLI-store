"""B站 WBI 签名（用于 /x/space/wbi/* 等接口）"""

import hashlib
import re
import time
from typing import Any, Dict, Optional, Tuple

from social_monitor.utils.http_client import HttpClient
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_KEY_PATTERN = re.compile(r"/([^/]+)\.(png|jpg|webp)$", re.I)
_WBI_KEYS_TTL = 3600
_BILIBILI_HOME = "https://www.bilibili.com/"


def _extract_key_from_url(url: str) -> str:
    match = _KEY_PATTERN.search(url or "")
    if not match:
        raise ValueError(f"无法从 WBI URL 解析 key: {url}")
    return match.group(1)


def get_mixin_key(orig: str) -> str:
    """对 img_key + sub_key 打乱编码得到 mixin_key"""
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _encode_wbi_value(value: Any) -> str:
    return "".join(ch for ch in str(value) if ch not in "!'()*")


def encode_uri_component(value: str) -> str:
    """与 JS encodeURIComponent 一致，百分号编码大写"""
    result = []
    for ch in value:
        code = ord(ch)
        if (
            48 <= code <= 57
            or 65 <= code <= 90
            or 97 <= code <= 122
            or ch in "-_.!~*'()"
        ):
            result.append(ch)
        else:
            for byte in ch.encode("utf-8"):
                result.append(f"%{byte:02X}")
    return "".join(result)


def build_wbi_query(params: Dict[str, Any]) -> str:
    """构建 WBI 签名用 query 字符串"""
    return "&".join(
        f"{encode_uri_component(k)}={encode_uri_component(v)}"
        for k, v in sorted(params.items())
    )


def sign_wbi_params(params: Dict[str, Any], img_key: str, sub_key: str) -> Dict[str, Any]:
    """为请求参数添加 wts / w_rid"""
    signed = dict(params)
    signed["wts"] = round(time.time())
    signed = {k: _encode_wbi_value(v) for k, v in sorted(signed.items())}
    query = build_wbi_query(signed)
    mixin_key = get_mixin_key(img_key + sub_key)
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed


class BilibiliWbiSigner:
    """获取并缓存 WBI img/sub key"""

    NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

    def __init__(self, http_client: HttpClient):
        self._http_client = http_client
        self._keys: Optional[Tuple[str, str]] = None
        self._keys_ts: float = 0.0
        self._warmed_up = False

    def _warmup_cookies(self) -> None:
        if self._warmed_up:
            return
        logger.debug("预热 B站 Cookie (buvid3)")
        self._http_client.get(_BILIBILI_HOME)
        self._warmed_up = True

    def get_keys(self, force_refresh: bool = False) -> Tuple[str, str]:
        now = time.time()
        if not force_refresh and self._keys and now - self._keys_ts < _WBI_KEYS_TTL:
            return self._keys

        self._warmup_cookies()
        logger.debug("刷新 B站 WBI keys")
        resp = self._http_client.get(
            self.NAV_URL,
            headers={"Referer": _BILIBILI_HOME},
        )
        data = resp.json()
        wbi_img = (data.get("data") or {}).get("wbi_img") or {}
        img_key = _extract_key_from_url(wbi_img.get("img_url", ""))
        sub_key = _extract_key_from_url(wbi_img.get("sub_url", ""))
        self._keys = (img_key, sub_key)
        self._keys_ts = now
        logger.debug("WBI keys 已更新 img=%s sub=%s", img_key[:8], sub_key[:8])
        return self._keys

    def sign(self, params: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
        img_key, sub_key = self.get_keys(force_refresh=force_refresh)
        return sign_wbi_params(params, img_key, sub_key)
