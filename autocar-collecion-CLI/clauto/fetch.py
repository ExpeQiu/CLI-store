"""统一 HTTP / scrapling 抓取层"""

import hashlib
import logging
import os
import subprocess
import tempfile
import time
from typing import Optional

import requests

from clauto.config import DEFAULT_USER_AGENT, get_cache_dir, get_scrapling_bin

logger = logging.getLogger("clauto.fetch")

MIN_HTML_LENGTH = 3000
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _read_cache(url: str) -> Optional[str]:
    cache_file = get_cache_dir() / f"{_cache_key(url)}.html"
    if cache_file.exists():
        logger.debug("命中缓存: %s", url)
        return cache_file.read_text(encoding="utf-8", errors="replace")
    return None


def _write_cache(url: str, html: str) -> None:
    cache_file = get_cache_dir() / f"{_cache_key(url)}.html"
    cache_file.write_text(html, encoding="utf-8")
    logger.debug("已缓存: %s -> %s", url, cache_file)


def fetch_with_scrapling(url: str, timeout: int = 30) -> Optional[str]:
    """通过 scrapling 动态抓取（处理 JS 渲染）"""
    scrapling_bin = get_scrapling_bin()
    if not scrapling_bin:
        logger.warning("scrapling 未安装，请 brew install scrapling 或设置 SCRAPLING_BIN")
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            tmp_path = f.name
        cmd = [
            scrapling_bin,
            "extract", "fetch",
            url, tmp_path,
            "--no-headless",
            "--disable-resources",
            "--network-idle",
            "--timeout", str(timeout * 1000),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        if result.returncode != 0:
            logger.warning("scrapling 错误: %s", (result.stderr or result.stdout)[:200])
            return None
        with open(tmp_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error("scrapling 抓取失败 [%s]: %s", url, e)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _requests_get(url: str, timeout: int) -> Optional[str]:
    resp = requests.get(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_page(
    url: str,
    timeout: int = 15,
    *,
    force_scrapling: bool = False,
    use_cache: bool = True,
    retries: int = DEFAULT_RETRIES,
) -> Optional[str]:
    """
    混合抓取：requests 优先，内容不足或失败时降级 scrapling。
    支持重试与 HTML 缓存。
    """
    if use_cache:
        cached = _read_cache(url)
        if cached:
            return cached

    last_error = None
    for attempt in range(retries + 1):
        try:
            if force_scrapling:
                html = fetch_with_scrapling(url, timeout)
            else:
                html = _requests_get(url, timeout)
                if html and len(html) < MIN_HTML_LENGTH:
                    logger.info("requests 返回内容过少 (%d bytes)，尝试 scrapling", len(html))
                    html = fetch_with_scrapling(url, timeout) or html

            if html:
                if use_cache:
                    _write_cache(url, html)
                return html
        except Exception as e:
            last_error = e
            logger.warning("抓取失败 (attempt %d/%d): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                time.sleep(DEFAULT_RETRY_DELAY)

    if not force_scrapling:
        logger.info("requests 全部失败，最后尝试 scrapling")
        html = fetch_with_scrapling(url, timeout)
        if html:
            if use_cache:
                _write_cache(url, html)
            return html

    if last_error:
        logger.error("抓取最终失败 [%s]: %s", url, last_error)
    return None
