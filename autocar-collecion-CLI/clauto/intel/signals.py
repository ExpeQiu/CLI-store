"""抓取信号 → intel_pre_launch 行映射"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# 常见车企/品牌（用于标题解析）
KNOWN_BRANDS = [
    "比亚迪", "吉利", "银河", "极氪", "Zeekr", "蔚来", "NIO", "小鹏", "XPeng",
    "理想", "Li Auto", "小米", "小米汽车", "华为", "问界", "AITO", "智界",
    "特斯拉", "Tesla", "长安", "深蓝", "阿维塔", "广汽", "埃安", "昊铂",
    "上汽", "荣威", "名爵", "智己", "IM", "东风", "岚图", "猛士",
    "长城", "魏牌", "坦克", "哈弗", "欧拉", "奇瑞", "星途", "捷途",
    "一汽", "红旗", "大众", "VW", "丰田", "Toyota", "本田", "Honda",
    "宝马", "BMW", "奔驰", "Mercedes", "奥迪", "Audi", "保时捷", "Porsche",
    "REDMI", "红米", "领克", "Lynk", "零跑", "Leapmotor", "哪吒", "NETA",
    "极狐", "ARCFOX", "飞凡", "Rising", "合创", "HYCAN",
]

_LAUNCH_PATTERNS = (
    r"(上市|发布|开售|亮相|预售|首发|亮相|全球首发|正式发布|新品发布)",
    r"(新款|年度改款|焕新|升级)",
)


def make_record_id(source: str, key: str) -> str:
    digest = hashlib.sha256(f"{source}:{key}".encode()).hexdigest()[:24]
    return f"clauto:{source}:{digest}"


def extract_brand_model(title: str) -> tuple[str | None, str | None]:
    text = title.strip()
    brand: str | None = None
    for b in KNOWN_BRANDS:
        if b in text:
            brand = b
            break
    if not brand:
        return None, None

    rest = text.split(brand, 1)[-1]
    rest = re.sub(r"[\s，,。！!？?：:（）()【】\[\]""\"']", " ", rest)
    tokens = [t for t in rest.split() if len(t) >= 2]
    model: str | None = None
    for tok in tokens:
        if any(p in tok for p in ("上市", "发布", "开售", "预售", "款")):
            tok = re.split("|".join(_LAUNCH_PATTERNS), tok)[0].strip()
        if len(tok) >= 2 and not re.fullmatch(r"\d{4}", tok):
            model = tok[:40]
            break
    if not model:
        m = re.search(rf"{re.escape(brand)}([\u4e00-\u9fa5A-Za-z0-9\-]+)", text)
        if m:
            model = m.group(1)[:40]
    return brand, model


def miit_to_row(item: dict[str, Any]) -> dict[str, str | None] | None:
    title = (item.get("title") or "").strip()
    link = (item.get("link") or title).strip()
    if not title:
        return None
    brand, model = extract_brand_model(title)
    if not brand and not model:
        # 目录类公告仍入库，便于后续人工关联
        brand = "待识别"
        model = title[:60]
    return {
        "车企": brand,
        "车型": model or title[:60],
        "发布类型": "工信部信号",
        "预计发布日期": item.get("date") or None,
        "配置亮点": title[:500],
        "分析状态": "待分析",
        "分析师": "clauto:miit",
        "_record_key": link,
    }


def news_to_row(item: dict[str, Any]) -> dict[str, str | None] | None:
    title = (item.get("title") or "").strip()
    url = (item.get("url") or title).strip()
    if not title:
        return None
    brand, model = extract_brand_model(title)
    launch_type = "新闻信号"
    if any(k in title for k in ("上市", "发布", "开售", "预售")):
        launch_type = "全新上市"
    elif "改款" in title or "焕新" in title:
        launch_type = "年度改款"
    summary = (item.get("summary") or "")[:300]
    highlight = title if not summary else f"{title} — {summary}"
    return {
        "车企": brand or "待识别",
        "车型": model or title[:60],
        "发布类型": launch_type,
        "预计发布日期": item.get("date") or None,
        "配置亮点": highlight[:500],
        "分析状态": "待分析",
        "分析师": f"clauto:news:{item.get('source', 'unknown')}",
        "_record_key": url,
    }


def monitor_to_patch(info: dict[str, Any]) -> dict[str, str | None]:
    config = info.get("config") or {}
    power = config.get("电池类型") or config.get("动力")
    assist = config.get("智能驾驶")
    return {
        "价格区间": info.get("price"),
        "动力类型": power,
        "智驾等级": assist,
    }
