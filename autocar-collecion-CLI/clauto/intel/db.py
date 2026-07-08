"""PostgreSQL 连接与执行"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from clauto.intel.config import DATABASE_URL

logger = logging.getLogger("clauto.intel.db")


def _connect():
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        raise RuntimeError(
            "intel 命令需要 PostgreSQL 支持，请安装: pip install -e '.[postgres]'"
        ) from e
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


@contextmanager
def get_connection() -> Iterator[Any]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_sql_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    logger.info("执行 SQL: %s", path)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("SQL 执行完成: %s", path.name)


def fetch_one(query: str, params: tuple | None = None) -> tuple | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetch_all(query: str, params: tuple | None = None) -> list[tuple]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def table_exists(table: str) -> bool:
    row = fetch_one(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (table,),
    )
    return row is not None


def column_exists(table: str, column: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return row is not None
