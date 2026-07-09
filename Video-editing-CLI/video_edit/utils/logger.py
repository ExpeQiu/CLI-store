"""日志与 exit code。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DEPENDENCY = 3


def setup_logger(verbose: bool = False, quiet: bool = False) -> None:
    logger.remove()
    if quiet:
        level = "WARNING"
    elif verbose:
        level = "DEBUG"
    else:
        level = "INFO"
    logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level:<7} | {message}")


def task_logger(log_dir: Path, stage: str):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{stage}.log"
    sink_id = logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}",
        encoding="utf-8",
    )
    return log_file, sink_id


def remove_sink(sink_id: int) -> None:
    try:
        logger.remove(sink_id)
    except ValueError:
        pass
