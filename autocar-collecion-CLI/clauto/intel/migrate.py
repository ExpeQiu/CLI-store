"""schema 迁移与 sibling 表回填"""

from __future__ import annotations

import logging
from pathlib import Path

from clauto.intel import db

logger = logging.getLogger("clauto.intel.migrate")

SIM_SQL_DIR = Path(__file__).resolve().parents[4] / "03T" / "SIM" / "scripts" / "sql"


def _sim_sql(name: str) -> Path:
    p = SIM_SQL_DIR / name
    if p.exists():
        return p
    # 开发机路径备选
    alt = Path("/Volumes/Lexar/git/03T/SIM/scripts/sql") / name
    if alt.exists():
        return alt
    raise FileNotFoundError(f"找不到迁移脚本: {name}（期望 {p}）")


def run_migrate(*, dry_run: bool = False) -> dict:
    """执行 SIM SQL 迁移 + 创建分析视图"""
    files = [
        "001_intel_pre_launch_migrate.sql",
        "002_gap_analysis_views.sql",
        "004_event_metadata.sql",
        "007_intel_backfill_fuzzy.sql",
    ]
    if dry_run:
        logger.info("[DRY RUN] 将执行: %s", files)
        return {"dry_run": True, "files": files}

    if not db.table_exists("intel_pre_launch"):
        raise RuntimeError("intel_pre_launch 表不存在，请先导入 intel 数据")

    for name in files:
        db.execute_sql_file(_sim_sql(name))

    stats = get_backfill_stats()
    logger.info("迁移完成: %s", stats)
    return {"migrated": True, **stats}


def get_backfill_stats() -> dict:
    row = db.fetch_one(
        """
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE 动力类型 IS NOT NULL AND trim(动力类型) != '') AS power,
            count(*) FILTER (WHERE 价格区间 IS NOT NULL AND trim(价格区间) != '') AS price,
            count(*) FILTER (WHERE 平台 IS NOT NULL AND trim(平台) != '') AS platform,
            count(*) FILTER (WHERE 智驾等级 IS NOT NULL AND trim(智驾等级) != '') AS adas,
            count(*) FILTER (WHERE 预计发布日期_norm IS NOT NULL) AS launch_date
        FROM intel_pre_launch
        """
    )
    if not row:
        return {}
    keys = ["total", "动力类型", "价格区间", "平台", "智驾等级", "预计发布日期"]
    return dict(zip(keys, row))


def run_backfill_only() -> dict:
    """仅重新执行 sibling 回填（不删列）"""
    sql = """
    UPDATE intel_pre_launch p SET
        动力类型 = COALESCE(NULLIF(trim(p.动力类型), ''), f.动力类型),
        价格区间 = COALESCE(NULLIF(trim(p.价格区间), ''), f.价格),
        updated_at = CURRENT_TIMESTAMP
    FROM (
        SELECT DISTINCT ON (品牌, 车型) 品牌, 车型, 动力类型, 价格
        FROM intel_focus_vehicles
        WHERE (动力类型 IS NOT NULL AND trim(动力类型) != '')
           OR (价格 IS NOT NULL AND trim(价格) != '')
        ORDER BY 品牌, 车型, id DESC
    ) f
    WHERE p.车企 = f.品牌 AND p.车型 = f.车型;

    UPDATE intel_pre_launch p SET
        平台 = COALESCE(NULLIF(trim(p.平台), ''), po.核心技术_平台),
        智驾等级 = COALESCE(NULLIF(trim(p.智驾等级), ''), po.核心技术_智驾),
        updated_at = CURRENT_TIMESTAMP
    FROM (
        SELECT DISTINCT ON (车企_品牌, 车型) 车企_品牌, 车型, 核心技术_平台, 核心技术_智驾
        FROM intel_post_launch
        WHERE (核心技术_平台 IS NOT NULL AND trim(核心技术_平台) != '')
           OR (核心技术_智驾 IS NOT NULL AND trim(核心技术_智驾) != '')
        ORDER BY 车企_品牌, 车型, id DESC
    ) po
    WHERE p.车企 = po.车企_品牌 AND p.车型 = po.车型;
    """
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    return get_backfill_stats()
