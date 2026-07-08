"""
工信部公告抓取模块
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import bs4

from clauto.fetch import fetch_page
from clauto.formatters import source_banner, wrap_json
from clauto.result import SOURCE_DEMO, SOURCE_EMPTY, SOURCE_LIVE, ScrapeResult

logger = logging.getLogger("clauto.miit")

MIIT_INDEX_URL = "https://www.miit.gov.cn/zwgk/zcwj/wjfb/index.html"
MIIT_BASE_URL = "https://www.miit.gov.cn"

# 工信部列表页常见容器选择器
LIST_SELECTORS = [
    ".xxgk_list li",
    ".list_cont li",
    ".c_list li",
    "ul.list li",
    ".article-list li",
    ".zfxxgk_item",
]

DEMO_ANNOUNCEMENTS = [
    {
        "title": "工业和信息化部关于发布2026年新能源汽车推广应用推荐车型目录的公告",
        "date": "2026-06-10",
        "link": "https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_1234567890.html",
        "summary": "现发布《新能源汽车推广应用推荐车型目录》（2026年第6批），共收录车型245个。",
    },
    {
        "title": "关于《新能源汽车生产企业及产品准入管理规定》的实施意见",
        "date": "2026-06-05",
        "link": "https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_2345678901.html",
        "summary": "进一步明确新能源汽车生产企业及产品准入管理的相关要求。",
    },
    {
        "title": "关于下达2026年第一批稀土开采、冶炼分离总量的通知",
        "date": "2026-06-03",
        "link": "https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_3456789012.html",
        "summary": "确定了2026年第一批稀土开采、冶炼分离总量控制指标。",
    },
    {
        "title": "关于组织开展2026年工业互联网试点示范项目申报工作的通知",
        "date": "2026-05-28",
        "link": "https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_4567890123.html",
        "summary": "组织开展2026年工业互联网试点示范项目申报，聚焦平台化设计、数字化管理等方向。",
    },
    {
        "title": "工业和信息化部关于公布2025年度中小企业公共服务示范平台名单的通告",
        "date": "2026-05-20",
        "link": "https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_5678901234.html",
        "summary": "经评审，确定196个平台为2025年度中小企业公共服务示范平台。",
    },
]


def parse_date(date_str: str) -> Optional[datetime]:
    """解析日期字符串"""
    patterns = [
        (r"%Y-%m-%d", r"(\d{4}-\d{1,2}-\d{1,2})"),
        (r"%Y年%m月%d日", r"(\d{4}年\d{1,2}月\d{1,2}日)"),
    ]
    for fmt, pat in patterns:
        m = re.search(pat, date_str)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                continue
    return None


def _normalize_link(href: str, page_url: str) -> str:
    if href.startswith("/"):
        return MIIT_BASE_URL + href
    if href.startswith("http"):
        return href
    return urljoin(page_url, href)


def _extract_from_list_item(item, page_url: str) -> Optional[dict]:
    """从列表项提取公告"""
    a = item.find("a", href=True)
    if not a:
        return None
    title = a.get_text(strip=True)
    href = a.get("href", "")
    if not title or len(title) < 6 or "javascript" in href.lower():
        return None

    link = _normalize_link(href, page_url)
    text = item.get_text(" ", strip=True)
    date_str = ""
    m = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)", text)
    if m:
        date_str = m.group(1)

    pub_date = parse_date(date_str)
    return {
        "title": title,
        "date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
        "link": link,
        "summary": "",
        "_pub_date": pub_date,
    }


def _parse_page(html: str, page_url: str, start_date: datetime, end_date: datetime) -> list[dict]:
    """解析单页公告列表"""
    soup = bs4.BeautifulSoup(html, "html.parser")
    results = []
    seen_titles: set[str] = set()

    # 优先使用列表容器选择器
    items = []
    for sel in LIST_SELECTORS:
        items = soup.select(sel)
        if items:
            logger.debug("使用选择器 %s 找到 %d 项", sel, len(items))
            break

    if items:
        for item in items:
            ann = _extract_from_list_item(item, page_url)
            if not ann or ann["title"] in seen_titles:
                continue
            pub_date = ann.pop("_pub_date", None)
            if pub_date and not (start_date < pub_date <= end_date):
                continue
            if not pub_date:
                ann["date"] = end_date.strftime("%Y-%m-%d")
            seen_titles.add(ann["title"])
            results.append(ann)
    else:
        # 降级：遍历链接，过滤 miit.gov.cn 政策文件
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or len(title) < 8 or "javascript" in href.lower():
                continue
            if title in seen_titles:
                continue
            link = _normalize_link(href, page_url)
            if "miit.gov.cn" not in link:
                continue
            if not any(k in link for k in ("/zcwj/", "/wjfb/", "/gg/", "/art/")):
                continue

            parent = a.find_parent(["li", "div", "p", "tr"])
            date_str = ""
            if parent:
                m = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)", parent.get_text())
                if m:
                    date_str = m.group(1)
            pub_date = parse_date(date_str)
            if pub_date and not (start_date < pub_date <= end_date):
                continue

            seen_titles.add(title)
            results.append({
                "title": title,
                "date": pub_date.strftime("%Y-%m-%d") if pub_date else end_date.strftime("%Y-%m-%d"),
                "link": link,
                "summary": "",
            })

    return results


def scrape_announcements(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_pages: int = 5,
    demo: bool = False,
) -> ScrapeResult[list[dict]]:
    """抓取工信部公告列表"""
    if end_date is None:
        end_date = datetime.today()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    if demo:
        logger.info("demo 模式：返回内置示例数据")
        results = []
        for ann in DEMO_ANNOUNCEMENTS:
            ann_date = parse_date(ann["date"])
            if ann_date and start_date < ann_date <= end_date:
                results.append({k: v for k, v in ann.items()})
        return ScrapeResult(data=results, source=SOURCE_DEMO)

    results: list[dict] = []
    warnings: list[str] = []
    page = 1

    while page <= max_pages:
        url = MIIT_INDEX_URL if page == 1 else f"{MIIT_BASE_URL}/zwgk/zcwj/wjfb/index_{page}.html"
        logger.info("抓取第 %d 页: %s", page, url)
        html = fetch_page(url, force_scrapling=(page == 1))
        if html is None:
            warnings.append(f"第 {page} 页抓取失败")
            break

        page_results = _parse_page(html, url, start_date, end_date)
        if not page_results:
            logger.info("第 %d 页无新数据，停止翻页", page)
            break
        results.extend(page_results)
        page += 1

    # 去重
    seen = set()
    unique = []
    for ann in results:
        if ann["title"] not in seen:
            seen.add(ann["title"])
            unique.append(ann)

    unique.sort(key=lambda x: x["date"], reverse=True)
    logger.info("共抓取 %d 条公告", len(unique))

    source = SOURCE_LIVE if unique else SOURCE_EMPTY
    return ScrapeResult(data=unique, source=source, warnings=warnings)


def to_markdown(result: ScrapeResult[list[dict]]) -> str:
    """生成 Markdown 格式报告"""
    announcements = result.data
    if not announcements:
        return f"**未找到符合条件的公告**\n\n{source_banner(result.source, result.warnings)}"

    lines = [
        "# 工信部公告\n",
        source_banner(result.source, result.warnings),
        f"> 抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 共 {len(announcements)} 条\n",
        "---",
        "",
    ]
    for i, ann in enumerate(announcements, 1):
        lines.append(f"### {i}. {ann['title']}")
        lines.append(f"- **日期**: {ann['date']}")
        lines.append(f"- **链接**: {ann['link']}")
        if ann.get("summary"):
            lines.append(f"- **摘要**: {ann['summary']}")
        lines.append("")
    return "\n".join(lines)


def to_json(result: ScrapeResult[list[dict]]) -> str:
    """生成 JSON 格式报告"""
    return wrap_json(
        "announcements", result.data,
        module="miit",
        data_source=result.source,
        warnings=result.warnings,
    )
