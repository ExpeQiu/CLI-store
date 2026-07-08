"""github-trend CLI 入口"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from github_trend.__version__ import __version__
from github_trend.collectors.github import fetch_trending, fetch_high_stars
from github_trend.collectors.feishu_bitable import sync_to_bitable
from github_trend.utils.errors import EXIT_ERROR, EXIT_NO_DATA, EXIT_OK, EXIT_SCRAPE_FAIL
from github_trend.utils.logger import setup_logger

logger = setup_logger()
_FORMATS = ("json", "table", "markdown")


def _render_table(payload: dict) -> str:
    lines = [f"# GitHub Trending ({payload.get('since', 'daily')})"]
    for item in payload.get("items", []):
        lines.append(f"{item['rank']}. {item['repo']} (+{item.get('stars_today', 0)})")
        if item.get("description"):
            lines.append(f"   {item['description']}")
    return "\n".join(lines)


def _emit(payload: dict, fmt: str, output_file: Optional[str]) -> int:
    if fmt == "json":
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    elif fmt == "markdown":
        text = _render_table(payload)
    else:
        text = _render_table(payload)

    if output_file:
        Path(output_file).expanduser().write_text(text, encoding="utf-8")
        click.echo(f"已写入 {output_file}", err=True)
    else:
        click.echo(text)

    if not payload.get("items") and payload.get("data_source") == "live":
        return EXIT_NO_DATA
    return EXIT_OK


@click.group()
@click.version_option(version=__version__, prog_name="github-trend")
@click.option("-v", "--verbose", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def cli(ctx, verbose: bool, quiet: bool):
    """GitHub 热门仓库趋势采集 CLI"""
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)


@cli.group()
def fetch():
    """采集数据"""


@fetch.command("trending")
@click.option("--since", default="daily", type=click.Choice(["daily", "weekly", "monthly"]))
@click.option("--language", default="", help="spoken language code，如 zh")
@click.option("--format", "fmt", default="json", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None, help="输出文件路径")
@click.option("--demo", is_flag=True, help="内置示例数据")
def fetch_trending_cmd(since, language, fmt, output, demo):
    """采集 GitHub Trending 近似榜单"""
    logger.info("fetch trending since=%s demo=%s", since, demo)
    try:
        payload = fetch_trending(since=since, spoken_language=language, demo=demo)
    except Exception:
        raise SystemExit(EXIT_SCRAPE_FAIL)
    raise SystemExit(_emit(payload, fmt, output))


@cli.group()
def bitable():
    """飞书 Bitable 同步"""


@bitable.command("sync")
@click.option("--demo", is_flag=True, help="使用内置示例数据，不访问外网")
@click.option("--dry-run", is_flag=True, help="只预览，不实际写入")
@click.option("--format", "fmt", default="json", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None, help="输出文件路径")
def bitable_sync(demo, dry_run, fmt, output):
    """
    采集 GitHub 高星项目并同步到飞书 Bitable。

    需要设置环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET。
    """
    logger.info("bitable sync demo=%s dry_run=%s", demo, dry_run)
    try:
        projects = fetch_high_stars(demo=demo)
    except Exception:
        logger.error("GitHub 数据采集失败")
        raise SystemExit(EXIT_SCRAPE_FAIL)

    if not projects:
        click.echo("无可同步的项目", err=True)
        raise SystemExit(EXIT_NO_DATA)

    result = sync_to_bitable(projects, dry_run=dry_run)

    payload = {
        "module": "github-trending-bitable-sync",
        "data_source": "demo" if demo else "live",
        "fetched_at": "",
        "count": len(projects),
        "items": projects,
        "sync_result": result,
        "dry_run": dry_run,
    }
    raise SystemExit(_emit(payload, fmt, output))


def main() -> int:
    try:
        cli(standalone_mode=False)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return EXIT_OK
        return int(code) if isinstance(code, int) else EXIT_ERROR
    except click.ClickException:
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
