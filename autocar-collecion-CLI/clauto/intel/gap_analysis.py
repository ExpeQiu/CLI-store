"""技术空白分析报告"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from clauto.intel import db

logger = logging.getLogger("clauto.intel.gap")


def _fetch_completeness() -> dict:
    row = db.fetch_one(
        """
        SELECT 总数, 有动力类型, 有价格区间, 有平台, 有智驾等级, 有发布日期
        FROM v_intel_pre_launch_completeness
        """
    )
    if not row:
        return {}
    keys = ["total", "power_type", "price_band", "platform", "adas", "launch_date"]
    return dict(zip(keys, row))


def _fetch_power_coverage() -> list[dict]:
    rows = db.fetch_all(
        "SELECT 动力类型, 车型数, 品牌数 FROM v_intel_power_type_coverage"
    )
    return [{"动力类型": r[0], "车型数": r[1], "品牌数": r[2]} for r in rows]


def _fetch_launch_windows(limit: int = 12) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT 发布月份, 预登记车型数, 涉及品牌
        FROM v_intel_launch_window
        ORDER BY 发布月份
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {"发布月份": str(r[0]), "预登记车型数": r[1], "涉及品牌": r[2]} for r in rows
    ]


def _fetch_tech_gaps_from_post_launch() -> list[dict]:
    """从 post_launch 核心技术字段提取高频技术词（S级亮点关联）"""
    rows = db.fetch_all(
        """
        SELECT 核心技术_电池, count(*) AS cnt
        FROM intel_post_launch
        WHERE 核心技术_电池 IS NOT NULL AND trim(核心技术_电池) != ''
        GROUP BY 核心技术_电池
        HAVING count(*) >= 2
        ORDER BY cnt DESC
        LIMIT 10
        """
    )
    return [{"技术": r[0][:80], "出现次数": r[1]} for r in rows]


def _fetch_missing_power_in_pre() -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT 车企, 车型, 发布类型, 分析状态
        FROM intel_pre_launch
        WHERE 动力类型 IS NULL OR trim(动力类型) = ''
        ORDER BY 车企, 车型
        LIMIT 20
        """
    )
    return [
        {"车企": r[0], "车型": r[1], "发布类型": r[2], "分析状态": r[3]} for r in rows
    ]


def generate_report() -> dict:
    if not db.table_exists("intel_pre_launch"):
        raise RuntimeError("intel_pre_launch 不存在")

    if not db.table_exists("v_intel_pre_launch_completeness"):
        raise RuntimeError("请先运行: clauto intel migrate")

    report = {
        "module": "intel-gap-analysis",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data_completeness": _fetch_completeness(),
        "power_type_coverage": _fetch_power_coverage(),
        "launch_window_crowding": _fetch_launch_windows(),
        "battery_tech_frequency": _fetch_tech_gaps_from_post_launch(),
        "missing_power_type_sample": _fetch_missing_power_in_pre(),
    }
    logger.info(
        "空白分析: total=%s power=%s price=%s",
        report["data_completeness"].get("total"),
        report["data_completeness"].get("power_type"),
        report["data_completeness"].get("price_band"),
    )
    return report


def to_markdown(report: dict) -> str:
    c = report.get("data_completeness", {})
    lines = [
        "# 技术空白分析报告",
        "",
        f"> 生成时间: {report.get('generated_at', '')}",
        "",
        "## 1. 数据完整度 (intel_pre_launch)",
        "",
        f"| 指标 | 数量 |",
        f"|------|------|",
        f"| 总记录 | {c.get('total', '-')} |",
        f"| 有动力类型 | {c.get('power_type', '-')} |",
        f"| 有价格区间 | {c.get('price_band', '-')} |",
        f"| 有平台 | {c.get('platform', '-')} |",
        f"| 有智驾等级 | {c.get('adas', '-')} |",
        f"| 有发布日期 | {c.get('launch_date', '-')} |",
        "",
        "## 2. 动力类型覆盖",
        "",
    ]
    for item in report.get("power_type_coverage", []):
        lines.append(f"- **{item['动力类型']}**: {item['车型数']} 款车型 / {item['品牌数']} 品牌")
    lines.extend(["", "## 3. 发布窗口拥挤度", ""])
    for w in report.get("launch_window_crowding", []):
        lines.append(f"- {w['发布月份']}: {w['预登记车型数']} 款 ({w['涉及品牌']})")
    lines.extend(["", "## 4. 竞品电池技术高频 (post_launch)", ""])
    for t in report.get("battery_tech_frequency", []):
        lines.append(f"- [{t['出现次数']}次] {t['技术']}")
    lines.extend(["", "## 5. 待补全动力类型 (样本)", ""])
    for m in report.get("missing_power_type_sample", []):
        lines.append(f"- {m['车企']} {m['车型']} ({m['发布类型']})")
    return "\n".join(lines) + "\n"


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
