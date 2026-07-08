"""
车型监测模块

监测车型价格、配置变化，支持竞品对比
"""

import json
import logging
import os
from copy import deepcopy
from datetime import datetime
from typing import Optional

from clauto.formatters import source_banner, wrap_json
from clauto.parsers import autohome
from clauto.result import SOURCE_DEMO, SOURCE_LIVE, ScrapeResult

logger = logging.getLogger("clauto.monitor")

DATA_SOURCES = {
    "autohome": {"name": "汽车之家", "parser": "autohome"},
    "yiche": {"name": "易车", "parser": None},
}

DEMO_MODEL_INFO = {
    "brand": "比亚迪",
    "model": "海豹",
    "price": "18.98-28.98万",
    "config": {
        "车身尺寸": "4800×1875×1460mm",
        "轴距": "2920mm",
        "电池类型": "磷酸铁锂",
        "续航里程": "550-700km",
        "驱动方式": "后驱/四驱",
        "智能驾驶": "DiPilot",
    },
}

DEMO_COMPETITORS = [
    {"brand": "特斯拉", "model": "Model 3", "price": "24.59-28.59万"},
    {"brand": "小米", "model": "SU7", "price": "21.59-29.99万"},
]


def scrape_model_info(
    brand: str,
    model: str,
    *,
    demo: bool = False,
    data_source: str = "autohome",
) -> ScrapeResult[dict]:
    """抓取车型信息"""
    if demo:
        info = deepcopy(DEMO_MODEL_INFO)
        info["brand"] = brand
        info["model"] = model
        return ScrapeResult(data=info, source=SOURCE_DEMO)

    if data_source != "autohome":
        return ScrapeResult(
            data={},
            source=SOURCE_LIVE,
            warnings=[f"数据源 {data_source} 尚未实现，请使用 autohome"],
        )

    info, warnings = autohome.scrape_model(brand, model)
    if info is None:
        return ScrapeResult(data={}, source=SOURCE_LIVE, warnings=warnings)

    return ScrapeResult(data=info, source=SOURCE_LIVE, warnings=warnings)


def scrape_competitors(
    competitors: list[str],
    *,
    demo: bool = False,
    data_source: str = "autohome",
) -> ScrapeResult[list[dict]]:
    """抓取竞品信息"""
    if demo:
        count = len(competitors) if competitors else 0
        return ScrapeResult(
            data=deepcopy(DEMO_COMPETITORS[:count]),
            source=SOURCE_DEMO,
        )

    results = []
    warnings: list[str] = []
    for comp in competitors:
        parts = comp.split(",")
        c_brand = parts[0].strip()
        c_model = parts[1].strip() if len(parts) > 1 else ""
        logger.info("抓取竞品: %s %s", c_brand, c_model)
        res = scrape_model_info(c_brand, c_model, demo=False, data_source=data_source)
        warnings.extend(res.warnings)
        results.append({
            "brand": c_brand,
            "model": c_model,
            "price": res.data.get("price", "未知") if res.data else "未知",
        })
    return ScrapeResult(data=results, source=SOURCE_LIVE, warnings=warnings)


def detect_changes(current: dict, baseline: Optional[dict] = None) -> list[dict]:
    """检测配置变更"""
    changes = []
    if baseline is None:
        return changes

    if current.get("price") != baseline.get("price"):
        changes.append({
            "item": "价格",
            "before": baseline.get("price", "未知"),
            "after": current.get("price", "未知"),
            "type": "价格变动",
        })

    curr_config = current.get("config", {})
    base_config = baseline.get("config", {})
    for key, val in curr_config.items():
        if key not in base_config:
            changes.append({"item": key, "before": "无", "after": val, "type": "新增"})
        elif base_config[key] != val:
            changes.append({
                "item": key,
                "before": base_config[key],
                "after": val,
                "type": "变更",
            })
    return changes


def _load_baseline(path: str) -> Optional[dict]:
    bf_path = os.path.expanduser(path)
    if os.path.exists(bf_path):
        with open(bf_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_baseline(path: str, data: dict) -> None:
    bf_path = os.path.expanduser(path)
    parent = os.path.dirname(bf_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(bf_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("已保存基线: %s", bf_path)


def monitor(
    brand: str,
    model: str,
    competitors: Optional[list[str]] = None,
    interval: Optional[str] = None,
    baseline_file: Optional[str] = None,
    save_baseline: bool = False,
    demo: bool = False,
    data_source: str = "autohome",
) -> ScrapeResult[dict]:
    """车型监测主函数"""
    logger.info("开始监测: %s %s (source=%s)", brand, model, data_source)
    warnings: list[str] = []

    if interval:
        warnings.append(f"监控间隔 {interval} 已记录，定时调度尚未实现")

    baseline = _load_baseline(baseline_file) if baseline_file else None
    if baseline_file and baseline is None:
        warnings.append(f"基线文件不存在: {baseline_file}，本次无对比基准")

    current_res = scrape_model_info(brand, model, demo=demo, data_source=data_source)
    warnings.extend(current_res.warnings)

    comp_res = ScrapeResult(data=[], source=current_res.source)
    if competitors:
        comp_res = scrape_competitors(competitors, demo=demo, data_source=data_source)
        warnings.extend(comp_res.warnings)

    current = current_res.data
    changes = detect_changes(current, baseline) if current else []

    if save_baseline and baseline_file and current:
        _save_baseline(baseline_file, current)

    report = {
        "brand": brand,
        "model": model,
        "report_time": datetime.now().isoformat(),
        "data_source": current_res.source,
        "interval": interval,
        "current": current,
        "changes": changes,
        "competitors": comp_res.data,
        "has_baseline": baseline is not None,
    }
    return ScrapeResult(data=report, source=current_res.source, warnings=warnings)


def to_markdown(result: ScrapeResult[dict]) -> str:
    """生成 Markdown 格式监测报告"""
    report = result.data
    lines = [
        "# 车型监测报告\n",
        source_banner(result.source, result.warnings),
        f"**品牌**: {report['brand']}",
        f"**车型**: {report['model']}",
        f"**生成时间**: {report['report_time']}",
    ]
    if not report.get("has_baseline"):
        lines.append("**基线状态**: 无历史基线（使用 --baseline 指定基线文件进行对比）")
    lines.extend(["", "---", "", "## 当前信息\n"])

    curr = report.get("current", {})
    if not curr:
        lines.append("**未能获取车型信息**")
    else:
        lines.append(f"- **价格**: {curr.get('price', '未知')}")
        if curr.get("config"):
            lines.append("### 配置参数")
            for k, v in curr["config"].items():
                lines.append(f"- **{k}**: {v}")
    lines.append("")

    changes = report.get("changes", [])
    if changes:
        lines.append("## 变更提醒\n")
        for ch in changes:
            lines.append(f"- **{ch['item']}**: {ch['before']} → {ch['after']} ({ch['type']})")
        lines.append("")
    else:
        lines.append("## 变更提醒\n**无明显变更**\n")

    competitors = report.get("competitors", [])
    if competitors:
        lines.append("## 竞品对比\n")
        lines.append("| 品牌 | 车型 | 价格 |")
        lines.append("|------|------|------|")
        for c in competitors:
            lines.append(f"| {c['brand']} | {c['model']} | {c['price']} |")
        lines.append("")

    return "\n".join(lines)


def to_json(result: ScrapeResult[dict]) -> str:
    """生成 JSON 格式监测报告"""
    return wrap_json(
        "report", result.data,
        module="monitor",
        data_source=result.source,
        warnings=result.warnings,
    )
