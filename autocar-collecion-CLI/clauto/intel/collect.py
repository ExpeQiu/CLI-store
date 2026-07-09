"""clauto 抓取信号直写 intel_pre_launch"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from clauto.intel import db
from clauto.intel.repository import enrich_by_brand_model, upsert_pre_launch
from clauto.intel.signals import make_record_id, miit_to_row, monitor_to_patch, news_to_row
from clauto.miit import scrape_announcements
from clauto.monitor import scrape_model_info
from clauto.news import deduplicate, scrape_news

logger = logging.getLogger("clauto.intel.collect")

DEFAULT_SOURCES = ("miit", "news")


def _upsert_rows(rows: list[dict[str, Any]], source: str) -> dict[str, int]:
    created = updated = skipped = 0
    for raw in rows:
        record_key = raw.pop("_record_key", None)
        if not record_key:
            skipped += 1
            continue
        if not raw.get("车企") and not raw.get("车型"):
            skipped += 1
            continue
        record_id = make_record_id(source, str(record_key))
        action = upsert_pre_launch(record_id, raw)
        if action == "created":
            created += 1
        else:
            updated += 1
        logger.debug(
            "upsert %s %s %s → %s",
            source,
            raw.get("车企"),
            raw.get("车型"),
            action,
        )
    return {"created": created, "updated": updated, "skipped": skipped}


def collect_miit(*, demo: bool = False, days: int = 7) -> dict[str, int]:
    end = datetime.now()
    start = end - timedelta(days=days)
    result = scrape_announcements(start_date=start, end_date=end, demo=demo)
    rows: list[dict[str, Any]] = []
    for item in result.data:
        row = miit_to_row(item)
        if row:
            rows.append(row)
    stats = _upsert_rows(rows, "miit")
    stats["fetched"] = len(result.data)
    logger.info(
        "miit collect: fetched=%d created=%d updated=%d skipped=%d",
        stats["fetched"],
        stats["created"],
        stats["updated"],
        stats["skipped"],
    )
    return stats


def collect_news(*, demo: bool = False, max_results: int = 20) -> dict[str, int]:
    total_created = total_updated = total_skipped = total_fetched = 0
    for source in ("industry", "new-energy"):
        result = scrape_news(source=source, max_results=max_results, demo=demo)
        result.data = deduplicate(result.data)
        rows: list[dict[str, Any]] = []
        for item in result.data:
            row = news_to_row(item)
            if row:
                rows.append(row)
        stats = _upsert_rows(rows, f"news-{source}")
        total_fetched += len(result.data)
        total_created += stats["created"]
        total_updated += stats["updated"]
        total_skipped += stats["skipped"]
        logger.info(
            "news/%s: fetched=%d created=%d updated=%d",
            source,
            len(result.data),
            stats["created"],
            stats["updated"],
        )
    return {
        "fetched": total_fetched,
        "created": total_created,
        "updated": total_updated,
        "skipped": total_skipped,
    }


def collect_monitor_enrich(
    watches: list[tuple[str, str]],
    *,
    demo: bool = False,
) -> dict[str, int]:
    """对 focus 车型抓取汽车之家并 enrich 已有 intel_pre_launch 行。"""
    enriched = 0
    failed = 0
    for brand, model in watches:
        result = scrape_model_info(brand, model, demo=demo)
        if not result.data:
            failed += 1
            logger.warning("monitor enrich 无数据: %s %s", brand, model)
            continue
        patch = {k: v for k, v in monitor_to_patch(result.data).items() if v}
        count = enrich_by_brand_model(
            brand,
            model,
            price=patch.get("价格区间"),
            power_type=patch.get("动力类型"),
            assist_level=patch.get("智驾等级"),
        )
        enriched += count
        logger.info("monitor enrich %s %s → %d 行", brand, model, count)
    return {"enriched": enriched, "failed": failed, "watched": len(watches)}


def run_collect(
    *,
    sources: list[str] | None = None,
    demo: bool = False,
    dry_run: bool = False,
    miit_days: int = 7,
    news_max: int = 20,
    watch: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if not db.table_exists("intel_pre_launch"):
        raise RuntimeError("intel_pre_launch 表不存在，请先导入 intel 数据或运行 clauto intel migrate")

    active = [s.strip().lower() for s in (sources or DEFAULT_SOURCES) if s.strip()]
    result: dict[str, Any] = {
        "module": "intel-collect",
        "sources": active,
        "demo": demo,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("[DRY] collect sources=%s demo=%s", active, demo)
        result["created"] = result["updated"] = result["skipped"] = 0
        return result

    if "miit" in active:
        result["miit"] = collect_miit(demo=demo, days=miit_days)
    if "news" in active:
        result["news"] = collect_news(demo=demo, max_results=news_max)
    if watch:
        result["monitor"] = collect_monitor_enrich(watch, demo=demo)

    result["created"] = sum(
        v.get("created", 0) for k, v in result.items() if isinstance(v, dict)
    )
    result["updated"] = sum(
        v.get("updated", 0) for k, v in result.items() if isinstance(v, dict)
    )
    result["skipped"] = sum(
        v.get("skipped", 0) for k, v in result.items() if isinstance(v, dict)
    )
    logger.info(
        "collect 完成: created=%d updated=%d skipped=%d",
        result["created"],
        result["updated"],
        result["skipped"],
    )
    return result
