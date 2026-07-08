"""汽车之家页面解析"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urljoin

import bs4

from clauto.fetch import fetch_page, fetch_with_scrapling

logger = logging.getLogger("clauto.parsers.autohome")

SEARCH_URL = "https://sou.autohome.com.cn/#type=1&value={brand}_{model}"
BASE_URL = "https://www.autohome.com.cn"

CONFIG_KEYWORDS = {
    "长": "车身尺寸",
    "轴距": "轴距",
    "电池": "电池类型",
    "续航": "续航里程",
    "驱动": "驱动方式",
    "智驾": "智能驾驶",
    "辅助驾驶": "智能驾驶",
}


def search_model_url(brand: str, model: str) -> Optional[str]:
    """搜索车型配置页 URL"""
    search_url = SEARCH_URL.format(brand=brand, model=model)
    logger.info("搜索车型: %s %s", brand, model)
    html = fetch_with_scrapling(search_url, timeout=25)
    if not html:
        return None

    soup = bs4.BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if "autohome.com.cn" in href and ("/specs/" in href or "/config/" in href):
            if brand in text or model in text or not text:
                return urljoin(BASE_URL, href) if href.startswith("/") else href
        if href.startswith("/") and ("/specs/" in href or "/config/" in href):
            if brand in text or model in text:
                return urljoin(BASE_URL, href)
    return None


def parse_model_page(html: str, brand: str, model: str) -> dict:
    """解析车型页价格与配置"""
    soup = bs4.BeautifulSoup(html, "html.parser")
    info: dict = {
        "brand": brand,
        "model": model,
        "price": "未知",
        "config": {},
    }

    price_selectors = [
        ".price", ".main-price", "[class*='price']",
        ".series-price", ".car-price",
    ]
    for sel in price_selectors:
        el = soup.select_one(sel)
        if el:
            price_text = el.get_text(strip=True)
            m = re.search(r"(\d+\.?\d*)\s*[-~至]\s*(\d+\.?\d*)\s*万", price_text)
            if m:
                info["price"] = f"{m.group(1)}-{m.group(2)}万"
                break

    if info["price"] == "未知":
        m = re.search(r"(\d+\.?\d*)\s*[-~至]\s*(\d+\.?\d*)\s*万", soup.get_text())
        if m:
            info["price"] = f"{m.group(1)}-{m.group(2)}万"

    for row in soup.select("tr, dl, .param-item, .config-item"):
        text = row.get_text(" ", strip=True)
        for keyword, field_name in CONFIG_KEYWORDS.items():
            if field_name and keyword in text:
                parts = re.split(r"[:：]", text, maxsplit=1)
                if len(parts) == 2 and field_name not in info["config"]:
                    val = parts[1].strip()[:80]
                    if val and len(val) > 1:
                        info["config"][field_name] = val

    return info


def scrape_model(brand: str, model: str) -> tuple[dict | None, list[str]]:
    """抓取并解析车型信息"""
    warnings: list[str] = []
    model_url = search_model_url(brand, model)
    if not model_url:
        warnings.append(f"未找到 {brand} {model} 的车型页面")
        return None, warnings

    logger.info("车型页: %s", model_url)
    html = fetch_with_scrapling(model_url, timeout=30)
    if not html:
        html = fetch_page(model_url, force_scrapling=False)
    if not html:
        warnings.append(f"车型页抓取失败: {model_url}")
        return None, warnings

    info = parse_model_page(html, brand, model)
    if info["price"] == "未知" and not info["config"]:
        warnings.append("未能解析价格或配置，页面结构可能已变化")
    return info, warnings
