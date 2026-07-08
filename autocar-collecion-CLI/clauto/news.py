"""
汽车新闻抓取模块

支持 Tavily API 搜索；无 Key 时明确报错，仅 --demo 使用内置数据
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree

import requests

from clauto.config import get_tavily_key
from clauto.formatters import source_banner, wrap_json
from clauto.result import SOURCE_DEMO, SOURCE_EMPTY, SOURCE_LIVE, ScrapeResult

logger = logging.getLogger("clauto.news")

DEMO_NEWS_INDUSTRY = [
    {
        "title": "工信部等五部门部署开展2026年新能源汽车下乡活动",
        "source": "汽车之家",
        "date": "2026-06-15",
        "url": "https://www.autohome.com.cn/news/202606/1234567.html",
        "summary": "工业和信息化部等五部门联合印发通知，组织开展2026年新能源汽车下乡活动。",
    },
    {
        "title": "欧盟对华电动汽车加征关税措施正式生效",
        "source": "36氪",
        "date": "2026-06-14",
        "url": "https://36kr.com/newsflash/12345678.html",
        "summary": "欧盟委员会宣布对从中国进口的电动汽车征收额外关税正式生效。",
    },
    {
        "title": "比亚迪5月销量再创新高，突破50万辆",
        "source": "盖世汽车",
        "date": "2026-06-13",
        "url": "https://news.gasgoo.com/china/202606/12345678.html",
        "summary": "比亚迪公布5月产销数据，新能源汽车销量达52万辆，同比增长38%。",
    },
    {
        "title": "宁德时代发布超充电池新品，10分钟可充400公里",
        "source": "第一电动",
        "date": "2026-06-12",
        "url": "https://d1ev.com/news/12456.html",
        "summary": "宁德时代发布神行PLUS超充电池，实现充电10分钟续航400公里。",
    },
    {
        "title": "小米汽车月交付量突破2万辆，SU7 Ultra开启预售",
        "source": "电动邦",
        "date": "2026-06-11",
        "url": "https://www.diangon.com/m/123456.html",
        "summary": "小米汽车宣布月交付量突破2万辆，SU7 Ultra版本正式开启预售。",
    },
]

DEMO_NEWS_NEWENERGY = [
    {
        "title": "比亚迪海豹2026款上市，标配城市NOA智驾",
        "source": "汽车之家",
        "date": "2026-06-15",
        "url": "https://www.autohome.com.cn/news/202606/1234570.html",
        "summary": "2026款比亚迪海豹正式上市，共推出4款配置，标配城市NOA智能驾驶。",
    },
    {
        "title": "特斯拉FSD即将在华推送，已完成数据安全评估",
        "source": "36氪",
        "date": "2026-06-14",
        "url": "https://36kr.com/newsflash/12345679.html",
        "summary": "特斯拉宣布FSD完全自动驾驶功能已完成中国监管部门数据安全评估。",
    },
    {
        "title": "宁德时代发布超充电池新品，10分钟可充400公里",
        "source": "第一电动",
        "date": "2026-06-12",
        "url": "https://d1ev.com/news/12456.html",
        "summary": "宁德时代发布神行PLUS超充电池，实现充电10分钟续航400公里。",
    },
    {
        "title": "国内充电桩保有量突破1200万台，桩车比1:1.2",
        "source": "中国汽车报",
        "date": "2026-06-10",
        "url": "https://www.chinabuses.com/news/202606/12345.html",
        "summary": "中国充电联盟公布数据，截至5月底全国充电桩保有量达1207万台。",
    },
]

SOURCE_KEYWORDS = {
    "industry": "汽车行业新闻",
    "new-energy": "新能源汽车新闻",
}

# RSS 备选源
RSS_FEEDS = {
    "industry": [
        "https://www.autohome.com.cn/rss/news.xml",
    ],
    "new-energy": [
        "https://www.d1ev.com/rss/news.xml",
    ],
}


def search_with_tavily(query: str, api_key: str, max_results: int = 10) -> Optional[list[dict]]:
    """通过 Tavily API 搜索新闻"""
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        news = []
        for r in results:
            news.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "summary": (r.get("content") or "")[:200],
                "source": r.get("source", ""),
                "date": r.get("published_date", ""),
            })
        return news if news else None
    except Exception as e:
        logger.error("Tavily 搜索失败: %s", e)
        return None


def _parse_rss(xml_text: str, max_results: int) -> list[dict]:
    """解析 RSS feed"""
    news = []
    try:
        root = ElementTree.fromstring(xml_text)
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            date_el = item.find("pubDate")
            if title_el is None or not title_el.text:
                continue
            title = title_el.text.strip()
            summary = ""
            if desc_el is not None and desc_el.text:
                summary = re.sub(r"<[^>]+>", "", desc_el.text)[:200]
            date_str = ""
            if date_el is not None and date_el.text:
                try:
                    date_str = datetime.strptime(
                        date_el.text.strip()[:25], "%a, %d %b %Y %H:%M:%S"
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    date_str = date_el.text.strip()[:10]
            news.append({
                "title": title,
                "url": (link_el.text or "").strip() if link_el is not None else "",
                "summary": summary,
                "source": "RSS",
                "date": date_str,
            })
            if len(news) >= max_results:
                break
    except ElementTree.ParseError as e:
        logger.warning("RSS 解析失败: %s", e)
    return news


def search_with_rss(source: str, max_results: int = 10) -> list[dict]:
    """尝试 RSS 源抓取"""
    feeds = RSS_FEEDS.get(source, [])
    all_news: list[dict] = []
    for feed_url in feeds:
        try:
            resp = requests.get(feed_url, timeout=15, headers={"User-Agent": "clauto/0.2"})
            resp.raise_for_status()
            items = _parse_rss(resp.text, max_results - len(all_news))
            all_news.extend(items)
            if len(all_news) >= max_results:
                break
        except Exception as e:
            logger.warning("RSS 抓取失败 [%s]: %s", feed_url, e)
    return all_news[:max_results]


def _filter_news(
    news_list: list[dict],
    keyword: str = "",
    date_str: Optional[str] = None,
) -> list[dict]:
    """关键词与日期过滤"""
    result = news_list
    if keyword:
        result = [
            n for n in result
            if keyword in n.get("title", "") or keyword in n.get("summary", "")
        ]
    if date_str:
        result = [n for n in result if n.get("date", "").startswith(date_str)]
    return result


def _demo_news(source: str, keyword: str, date_str: Optional[str], max_results: int) -> list[dict]:
    """内置演示数据"""
    pool = DEMO_NEWS_INDUSTRY if source == "industry" else DEMO_NEWS_NEWENERGY
    return _filter_news(pool, keyword, date_str)[:max_results]


def scrape_news(
    source: str = "industry",
    keyword: str = "",
    date_str: Optional[str] = None,
    max_results: int = 10,
    demo: bool = False,
) -> ScrapeResult[list[dict]]:
    """抓取汽车新闻"""
    warnings: list[str] = []

    if demo:
        logger.info("demo 模式：返回内置示例数据")
        data = _demo_news(source, keyword, date_str, max_results)
        return ScrapeResult(data=data, source=SOURCE_DEMO)

    # 1. Tavily API
    tavily_key = get_tavily_key()
    if tavily_key:
        query = f"{SOURCE_KEYWORDS.get(source, '汽车新闻')} {keyword} {date_str or ''}".strip()
        news = search_with_tavily(query, tavily_key, max_results)
        if news:
            data = _filter_news(news, keyword, date_str)[:max_results]
            return ScrapeResult(data=data, source=SOURCE_LIVE)

    # 2. RSS 备选
    logger.info("Tavily 不可用，尝试 RSS 源")
    rss_news = search_with_rss(source, max_results)
    if rss_news:
        data = _filter_news(rss_news, keyword, date_str)
        if not tavily_key:
            warnings.append("未配置 TAVILY_API_KEY，使用 RSS 源")
        return ScrapeResult(data=data, source=SOURCE_LIVE, warnings=warnings)

    # 3. 全部失败
    if not tavily_key:
        warnings.append("未配置 TAVILY_API_KEY，且 RSS 源不可用")
    else:
        warnings.append("Tavily 与 RSS 均未能获取新闻")
    return ScrapeResult(data=[], source=SOURCE_EMPTY, warnings=warnings)


def deduplicate(news_list: list[dict]) -> list[dict]:
    """基于标题+链接去重"""
    seen: set[str] = set()
    result = []
    for n in news_list:
        key = hashlib.md5((n["title"] + n.get("url", "")).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result


def to_markdown(result: ScrapeResult[list[dict]], source: str = "industry") -> str:
    """生成 Markdown 格式报告"""
    news_list = result.data
    source_labels = {"industry": "汽车行业新闻", "new-energy": "新能源汽车新闻"}
    label = source_labels.get(source, source)

    if not news_list:
        return f"**未找到符合条件的{label}**\n\n{source_banner(result.source, result.warnings)}"

    lines = [
        f"# {label}\n",
        source_banner(result.source, result.warnings),
        f"> 抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 共 {len(news_list)} 条\n",
        "---",
        "",
    ]
    for i, n in enumerate(news_list, 1):
        lines.append(f"### {i}. {n['title']}")
        lines.append(f"- **来源**: {n.get('source', '未知')}")
        lines.append(f"- **日期**: {n.get('date', '未知')}")
        lines.append(f"- **链接**: {n.get('url', '')}")
        if n.get("summary"):
            lines.append(f"- **摘要**: {n['summary']}")
        lines.append("")
    return "\n".join(lines)


def to_json(result: ScrapeResult[list[dict]]) -> str:
    """生成 JSON 格式报告"""
    return wrap_json(
        "news", result.data,
        module="news",
        data_source=result.source,
        warnings=result.warnings,
    )
