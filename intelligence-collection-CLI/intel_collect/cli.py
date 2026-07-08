"""intel-collect CLI 入口"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from intel_collect.__version__ import __version__
from intel_collect.collectors.feed import fetch_intel
from intel_collect.utils.errors import EXIT_ERROR, EXIT_NO_DATA, EXIT_OK, EXIT_SCRAPE_FAIL
from intel_collect.utils.logger import setup_logger

logger = setup_logger()
_FORMATS = ("json", "table", "markdown")


def _render_table(payload: dict) -> str:
    lines = ["# 情报采集"]
    for item in payload.get("items", []):
        lines.append(f"- [{item['source']}] {item['title']}")
    return "\n".join(lines)


def _emit(payload: dict, fmt: str, output_file: Optional[str]) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2) if fmt == "json" else _render_table(payload)
    if output_file:
        Path(output_file).expanduser().write_text(text, encoding="utf-8")
        click.echo(f"已写入 {output_file}", err=True)
    else:
        click.echo(text)
    if not payload.get("items") and payload.get("data_source") == "live":
        return EXIT_NO_DATA
    return EXIT_OK


@click.group()
@click.version_option(version=__version__, prog_name="intel-collect")
@click.option("-v", "--verbose", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def cli(verbose: bool, quiet: bool):
    """行业情报采集 CLI"""
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)


@cli.group()
def intel():
    """情报子命令"""


@intel.command("feed")
@click.option("--topic", default="", help="主题过滤")
@click.option("--limit", default=20, show_default=True)
@click.option("--format", "fmt", default="json", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None, help="输出文件")
@click.option("--demo", is_flag=True, help="内置示例数据")
def intel_feed(topic, limit, fmt, output, demo):
    """采集情报 feed"""
    logger.info("intel feed topic=%s demo=%s", topic or "(all)", demo)
    payload = fetch_intel(topic=topic, limit=limit, demo=demo)
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
