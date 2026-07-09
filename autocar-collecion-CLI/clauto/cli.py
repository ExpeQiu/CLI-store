#!/usr/bin/env python3
"""
clauto - CLI 入口
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from clauto.__version__ import __version__
from clauto.result import SOURCE_DEMO, SOURCE_EMPTY

logger = logging.getLogger("clauto")

# exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 2
EXIT_SCRAPE_FAIL = 3


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def parse_date_arg(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"日期格式错误，请使用 YYYY-MM-DD，实际收到: {s}"
        ) from e


def _output(args, content: str) -> None:
    if args.output:
        out_path = os.path.expanduser(args.output)
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("已保存到: %s", args.output)
    else:
        print(content)


def _resolve_exit(result, demo: bool) -> int:
    """根据抓取结果决定 exit code"""
    if demo or result.is_demo:
        return EXIT_OK
    if result.source == SOURCE_EMPTY:
        return EXIT_NO_DATA
    if not result.ok:
        return EXIT_SCRAPE_FAIL
    if result.warnings:
        return EXIT_OK  # 有数据但有警告，仍算成功
    return EXIT_OK


def cmd_miit(args) -> int:
    from clauto.miit import scrape_announcements, to_json as miit_json, to_markdown as miit_md

    start = parse_date_arg(args.start) if args.start else None
    end = parse_date_arg(args.end) if args.end else None
    if start and end and start > end:
        logger.error("起始日期不能晚于结束日期")
        return EXIT_ERROR

    logger.info(
        "开始抓取工信部公告 (范围: %s ~ %s)",
        args.start or "最近7天", args.end or "今天",
    )
    result = scrape_announcements(
        start_date=start, end_date=end,
        max_pages=args.pages, demo=args.demo,
    )

    if args.format == "json":
        content = miit_json(result)
    else:
        content = miit_md(result)

    _output(args, content)
    return _resolve_exit(result, args.demo)


def cmd_news(args) -> int:
    from clauto.news import deduplicate, scrape_news, to_json as news_json, to_markdown as news_md

    logger.info("抓取新闻: source=%s, keyword=%s", args.source, args.keyword or "无")
    result = scrape_news(
        source=args.source,
        keyword=args.keyword or "",
        date_str=args.date,
        max_results=args.max_results,
        demo=args.demo,
    )
    result.data = deduplicate(result.data)

    if args.format == "json":
        content = news_json(result)
    else:
        content = news_md(result, source=args.source)

    _output(args, content)
    return _resolve_exit(result, args.demo)


def cmd_intel_migrate(args) -> int:
    from clauto.intel.migrate import run_migrate

    result = run_migrate(dry_run=args.dry_run)
    if args.format == "json":
        import json
        _output(args, json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _output(args, f"迁移结果: {result}\n")
    return EXIT_OK


def cmd_intel_backfill(args) -> int:
    from clauto.intel.migrate import run_backfill_only

    result = run_backfill_only()
    if args.format == "json":
        import json
        _output(args, json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _output(args, f"回填统计: {result}\n")
    return EXIT_OK


def cmd_intel_collect(args) -> int:
    from clauto.intel.collect import run_collect

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    watch: list[tuple[str, str]] = []
    if args.watch:
        for pair in args.watch:
            parts = pair.split(",", 1)
            if len(parts) == 2:
                watch.append((parts[0].strip(), parts[1].strip()))

    result = run_collect(
        sources=sources,
        demo=args.demo,
        dry_run=args.dry_run,
        miit_days=args.miit_days,
        news_max=args.news_max,
        watch=watch or None,
    )
    if args.format == "json":
        import json
        _output(args, json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _output(args, f"collect 结果: {result}\n")
    return EXIT_OK


def cmd_intel_sync_bitable(args) -> int:
    from clauto.intel.bitable import sync_from_bitable

    result = sync_from_bitable(dry_run=args.dry_run, demo=args.demo)
    if args.format == "json":
        import json
        _output(args, json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _output(args, f"Bitable 同步: {result}\n")
    return EXIT_OK


def cmd_intel_bitable_fields(args) -> int:
    from clauto.intel.bitable import list_fields, list_tables
    from clauto.intel.config import FEISHU_INTEL_TABLE_ID

    table_id = args.table_id or FEISHU_INTEL_TABLE_ID
    if not table_id:
        tables = list_tables()
        lines = ["Bitable 表列表:", ""]
        for t in tables:
            lines.append(f"- {t.get('name')} → {t.get('table_id')}")
        _output(args, "\n".join(lines) + "\n")
        return EXIT_OK
    fields = list_fields(table_id)
    if args.format == "json":
        import json
        _output(args, json.dumps(fields, ensure_ascii=False, indent=2))
    else:
        lines = [f"表 {table_id} 字段:", ""]
        for f in fields:
            lines.append(f"- {f.get('field_name')} ({f.get('type')})")
        _output(args, "\n".join(lines) + "\n")
    return EXIT_OK


def cmd_intel_gap(args) -> int:
    from clauto.intel.gap_analysis import generate_report, to_json, to_markdown

    report = generate_report()
    if args.format == "json":
        _output(args, to_json(report))
    else:
        _output(args, to_markdown(report))
    return EXIT_OK


def cmd_monitor(args) -> int:
    from clauto.monitor import monitor, to_json as mon_json, to_markdown as mon_md

    competitors = None
    if args.competitors:
        comps = args.competitors.split(",")
        competitors = []
        i = 0
        while i < len(comps):
            brand = comps[i].strip()
            model = comps[i + 1].strip() if i + 1 < len(comps) else ""
            competitors.append(f"{brand},{model}")
            i += 2

    if args.save_baseline and not args.baseline:
        logger.error("--save-baseline 需要同时指定 --baseline 文件路径")
        return EXIT_ERROR

    result = monitor(
        brand=args.brand,
        model=args.model,
        competitors=competitors,
        interval=args.interval,
        baseline_file=args.baseline,
        save_baseline=args.save_baseline,
        demo=args.demo,
        data_source=args.source,
    )

    if args.format == "json":
        content = mon_json(result)
    else:
        content = mon_md(result)

    _output(args, content)

    if args.demo:
        return EXIT_OK
    if not result.data.get("current"):
        return EXIT_SCRAPE_FAIL
    return _resolve_exit(result, args.demo)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="输出格式 (默认 markdown)",
    )
    parser.add_argument("--output", "-o", type=str, default=None, help="输出文件路径")
    parser.add_argument(
        "--demo", action="store_true",
        help="使用内置示例数据（用于测试，无需网络）",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clauto",
        description="clauto - CLI automation toolkit (工信部公告 / 汽车新闻 / 车型监测)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅输出警告/错误")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    miit_p = subparsers.add_parser("miit", help="抓取工信部公告")
    miit_p.add_argument("--start", type=str, default=None, help="起始日期 (YYYY-MM-DD)")
    miit_p.add_argument("--end", type=str, default=None, help="结束日期 (YYYY-MM-DD)")
    miit_p.add_argument("--pages", type=int, default=5, help="最多翻页数 (默认 5)")
    _add_common_args(miit_p)

    news_p = subparsers.add_parser("news", help="抓取汽车新闻")
    news_p.add_argument(
        "--source", choices=["industry", "new-energy"],
        default="industry", help="新闻源类型",
    )
    news_p.add_argument("--keyword", "-k", type=str, default=None, help="关键词过滤")
    news_p.add_argument("--date", "-d", type=str, default=None, help="指定日期 (YYYY-MM-DD)")
    news_p.add_argument("--max-results", "-n", type=int, default=10, help="最大结果数")
    _add_common_args(news_p)

    mon_p = subparsers.add_parser("monitor", help="监测车型价格和配置")
    mon_p.add_argument("--brand", "-b", required=True, help="品牌（如 比亚迪）")
    mon_p.add_argument("--model", "-m", required=True, help="车型（如 海豹）")
    mon_p.add_argument(
        "--competitors", "-c", type=str, default=None,
        help="竞品: 品牌1,车型1,品牌2,车型2",
    )
    mon_p.add_argument("--interval", "-i", type=str, default=None, help="监控间隔（仅记录）")
    mon_p.add_argument(
        "--baseline", "-B", type=str, default=None,
        help="历史基线文件（用于对比变更，不会自动覆盖）",
    )
    mon_p.add_argument(
        "--save-baseline", action="store_true",
        help="将本次抓取结果保存为基线文件（需配合 --baseline）",
    )
    mon_p.add_argument(
        "--source", choices=["autohome", "yiche"],
        default="autohome", help="数据源 (默认 autohome)",
    )
    _add_common_args(mon_p)

    intel_p = subparsers.add_parser(
        "intel", help="情报层：PG 直写采集 / 迁移 / 技术空白分析",
    )
    intel_sub = intel_p.add_subparsers(dest="intel_command")

    mig_p = intel_sub.add_parser("migrate", help="修复 intel_pre_launch 字段并创建分析视图")
    mig_p.add_argument("--dry-run", action="store_true")
    _add_common_args(mig_p)

    bf_p = intel_sub.add_parser("backfill", help="从 focus_vehicles/post_launch 重新回填")
    _add_common_args(bf_p)

    col_p = intel_sub.add_parser(
        "collect",
        help="miit/news 抓取信号直写 intel_pre_launch（默认路径，不经过 Bitable）",
    )
    col_p.add_argument(
        "--sources",
        type=str,
        default="miit,news",
        help="采集源，逗号分隔: miit,news（默认 miit,news）",
    )
    col_p.add_argument("--miit-days", type=int, default=7, help="工信部公告回溯天数")
    col_p.add_argument("--news-max", type=int, default=20, help="每个新闻源最大条数")
    col_p.add_argument(
        "--watch",
        action="append",
        metavar="BRAND,MODEL",
        help="汽车之家 enrich：品牌,车型（可重复）",
    )
    col_p.add_argument("--dry-run", action="store_true")
    _add_common_args(col_p)

    sync_p = intel_sub.add_parser(
        "sync-bitable",
        help="[legacy] 从飞书 Bitable 同步到 intel_pre_launch",
    )
    sync_p.add_argument("--dry-run", action="store_true")
    _add_common_args(sync_p)

    fld_p = intel_sub.add_parser("bitable-fields", help="列出 Bitable 表/字段（需 FEISHU 凭证）")
    fld_p.add_argument("--table-id", type=str, default=None)
    _add_common_args(fld_p)

    gap_p = intel_sub.add_parser("gap-analysis", help="生成技术空白分析报告")
    _add_common_args(gap_p)

    args = parser.parse_args(argv)
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    if args.command is None:
        parser.print_help()
        return EXIT_OK

    if args.command == "intel":
        intel_handlers = {
            "migrate": cmd_intel_migrate,
            "backfill": cmd_intel_backfill,
            "collect": cmd_intel_collect,
            "sync-bitable": cmd_intel_sync_bitable,
            "bitable-fields": cmd_intel_bitable_fields,
            "gap-analysis": cmd_intel_gap,
        }
        if not args.intel_command:
            intel_p.print_help()
            return EXIT_OK
        handler = intel_handlers.get(args.intel_command)
        if handler is None:
            intel_p.print_help()
            return EXIT_ERROR
        try:
            return handler(args)
        except KeyboardInterrupt:
            logger.warning("用户中断")
            return EXIT_ERROR
        except RuntimeError as e:
            logger.error("%s", e)
            return EXIT_ERROR

    handlers = {"miit": cmd_miit, "news": cmd_news, "monitor": cmd_monitor}
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_ERROR

    try:
        return handler(args)
    except KeyboardInterrupt:
        logger.warning("用户中断")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
