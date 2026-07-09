"""飞书 Bitable → intel_pre_launch 同步"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from clauto.intel.config import (
    DEFAULT_FIELD_MAP,
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_INTEL_APP_TOKEN,
    FEISHU_INTEL_TABLE_ID,
)
from clauto.intel import db
from clauto.intel.repository import upsert_pre_launch

logger = logging.getLogger("clauto.intel.bitable")

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def _get_token() -> str:
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError("请配置 FEISHU_APP_ID 与 FEISHU_APP_SECRET")
    payload = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET})
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            headers={"Content-Type": "application/json"},
            content=payload,
        )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data.get('msg')}")
    return data["tenant_access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def list_tables(token: str | None = None) -> list[dict[str, Any]]:
    token = token or _get_token()
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{FEISHU_BASE}/bitable/v1/apps/{FEISHU_INTEL_APP_TOKEN}/tables",
            headers=_auth_headers(token),
            params={"page_size": 100},
        )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"List tables error: {data.get('msg')}")
    return data.get("data", {}).get("items", [])


def list_fields(table_id: str, token: str | None = None) -> list[dict[str, Any]]:
    token = token or _get_token()
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{FEISHU_BASE}/bitable/v1/apps/{FEISHU_INTEL_APP_TOKEN}/tables/{table_id}/fields",
            headers=_auth_headers(token),
            params={"page_size": 100},
        )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"List fields error: {data.get('msg')}")
    return data.get("data", {}).get("items", [])


def fetch_records(table_id: str, token: str | None = None) -> list[dict[str, Any]]:
    token = token or _get_token()
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    with httpx.Client(timeout=60.0) as client:
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = client.get(
                f"{FEISHU_BASE}/bitable/v1/apps/{FEISHU_INTEL_APP_TOKEN}/tables/{table_id}/records",
                headers=_auth_headers(token),
                params=params,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Fetch records error: {data.get('msg')}")
            chunk = data.get("data", {})
            items.extend(chunk.get("items", []))
            if not chunk.get("has_more"):
                break
            page_token = chunk.get("page_token")
    return items


def _unwrap_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [_unwrap_field(v) for v in value]
        return "、".join(p for p in parts if p) or None
    if isinstance(value, dict):
        for key in ("text", "name", "value", "link"):
            if key in value and value[key]:
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def map_record_fields(fields: dict[str, Any]) -> dict[str, str | None]:
    mapped: dict[str, str | None] = {}
    for bitable_name, raw in fields.items():
        pg_col = DEFAULT_FIELD_MAP.get(bitable_name)
        if not pg_col:
            continue
        mapped[pg_col] = _unwrap_field(raw)
    return mapped


def sync_from_bitable(*, dry_run: bool = False, demo: bool = False) -> dict[str, int]:
    if demo:
        logger.info("[DEMO] Bitable 同步示例")
        return {"created": 1, "updated": 0, "skipped": 0, "demo": True}

    table_id = FEISHU_INTEL_TABLE_ID
    if not table_id:
        tables = list_tables()
        if not tables:
            raise RuntimeError("Bitable 中无 table，请设置 FEISHU_INTEL_TABLE_ID")
        table_id = tables[0]["table_id"]
        logger.info("未配置 TABLE_ID，使用首个表: %s (%s)", tables[0].get("name"), table_id)

    records = fetch_records(table_id)
    logger.info("Bitable 拉取 %d 条记录", len(records))

    created = updated = skipped = 0
    for rec in records:
        record_id = rec.get("record_id")
        if not record_id:
            skipped += 1
            continue
        row = map_record_fields(rec.get("fields", {}))
        if not row.get("车企") and not row.get("车型"):
            skipped += 1
            continue
        if dry_run:
            logger.info("[DRY] %s | %s %s", record_id, row.get("车企"), row.get("车型"))
            continue
        action = upsert_pre_launch(record_id, row)
        if action == "created":
            created += 1
        else:
            updated += 1

    logger.info("同步完成: created=%d updated=%d skipped=%d", created, updated, skipped)
    return {"created": created, "updated": updated, "skipped": skipped}
