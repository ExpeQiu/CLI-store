"""intel_pre_launch 读写"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from clauto.intel import db

logger = logging.getLogger("clauto.intel.repository")


def parse_launch_date(raw: str | None) -> date | None:
    if not raw or raw == "0":
        return None
    if raw.isdigit():
        n = int(raw)
        if n > 1_000_000_000_000:
            return datetime.utcfromtimestamp(n / 1000).date()
        if n > 1_000_000_000:
            return datetime.utcfromtimestamp(n).date()
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def upsert_pre_launch(record_id: str, row: dict[str, str | None]) -> str:
    """按 record_id INSERT 或 UPDATE，返回 created | updated。"""
    cols = ["record_id"] + [k for k in row if k != "record_id"]
    values = [record_id] + [row.get(c) for c in cols[1:]]

    launch_raw = row.get("预计发布日期")
    launch_norm = parse_launch_date(launch_raw)

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM intel_pre_launch WHERE record_id = %s",
                (record_id,),
            )
            exists = cur.fetchone()
            if exists:
                set_parts: list[str] = []
                params: list[Any] = []
                for c in cols[1:]:
                    set_parts.append(f'"{c}" = %s')
                    params.append(row.get(c))
                if launch_norm:
                    set_parts.append("预计发布日期_norm = %s")
                    params.append(launch_norm)
                set_parts.append("updated_at = CURRENT_TIMESTAMP")
                params.append(record_id)
                cur.execute(
                    f'UPDATE intel_pre_launch SET {", ".join(set_parts)} WHERE record_id = %s',
                    params,
                )
                return "updated"

            insert_cols = cols.copy()
            insert_vals = values.copy()
            if launch_norm:
                insert_cols.append("预计发布日期_norm")
                insert_vals.append(launch_norm)
            placeholders = ", ".join(["%s"] * len(insert_vals))
            col_names = ", ".join(f'"{c}"' for c in insert_cols)
            cur.execute(
                f"INSERT INTO intel_pre_launch ({col_names}) VALUES ({placeholders})",
                insert_vals,
            )
            return "created"


def enrich_by_brand_model(
    brand: str,
    model: str,
    *,
    price: str | None = None,
    power_type: str | None = None,
    platform: str | None = None,
    assist_level: str | None = None,
) -> int:
    """按车企+车型批量 enrich 已有预登记行，返回更新行数。"""
    sets: list[str] = []
    params: list[Any] = []
    if price:
        sets.append('价格区间 = COALESCE(NULLIF(trim(价格区间), \'\'), %s)')
        params.append(price)
    if power_type:
        sets.append('动力类型 = COALESCE(NULLIF(trim(动力类型), \'\'), %s)')
        params.append(power_type)
    if platform:
        sets.append('平台 = COALESCE(NULLIF(trim(平台), \'\'), %s)')
        params.append(platform)
    if assist_level:
        sets.append('智驾等级 = COALESCE(NULLIF(trim(智驾等级), \'\'), %s)')
        params.append(assist_level)
    if not sets:
        return 0
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.extend([brand, model])
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE intel_pre_launch
                SET {", ".join(sets)}
                WHERE 车企 = %s AND 车型 = %s
                """,
                params,
            )
            return cur.rowcount
