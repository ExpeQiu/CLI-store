"""Feishu Bitable 写入模块"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("github_trend.collectors.feishu_bitable")

# Bitable 配置（支持环境变量覆盖）
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a93a91327978dbc6")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
APP_TOKEN = os.getenv("FEISHU_APP_TOKEN", "SsDwwmax9iD0epkhtGvcYS0xnUh")
TABLE_ID = os.getenv("FEISHU_TABLE_ID", "tblgGQ4OdYMJKaLG")

# 字段ID映射
FIELD_IDS = {
    "项目名": "fldvkMXvqm",
    "Stars": "fldCCeosbR",
    "语言": "flddu02IKw",
    "今日增长": "fldOtf2ErZ",
    "简介": "fldsc0AUkM",
    "链接": "fldCyOEV7P",
}


def _get_token() -> str:
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
            content=data,
        )
    d = resp.json()
    if d.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {d.get('msg')}")
    return d["tenant_access_token"]


def _get_records(token: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size=100",
            headers={"Authorization": f"Bearer {token}"},
        )
    d = resp.json()
    if d.get("code") != 0:
        raise RuntimeError(f"Get records error: {d.get('msg')}")
    return d.get("data", {}).get("items", [])


def _create_record(token: str, fields: dict) -> None:
    data = json.dumps({"fields": fields})
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Content-Length": str(len(data))},
            content=data,
        )
    d = resp.json()
    if d.get("code") != 0:
        raise RuntimeError(f"Create record error: {d.get('msg')}")


def _delete_record(token: str, record_id: str) -> None:
    with httpx.Client(timeout=30.0) as client:
        resp = client.delete(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    d = resp.json()
    if d.get("code") != 0:
        logger.warning("Delete record %s error: %s", record_id, d.get("msg"))


def sync_to_bitable(projects: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, int]:
    """
    将 GitHub 项目列表同步到飞书 Bitable。

    Returns:
        dict with keys: created, skipped, cleaned
    """
    if not projects:
        logger.warning("No projects to sync")
        return {"created": 0, "skipped": 0, "cleaned": 0}

    if dry_run:
        logger.info("[DRY RUN] 跳过飞书 API 调用")
        logger.info("[DRY] 共 %d 个项目待同步", len(projects))
        for p in projects[:5]:
            logger.info("[DRY]   - %s (%s⭐) %s", p.get("name"), p.get("stars"), p.get("url"))
        return {"created": len(projects), "skipped": 0, "cleaned": 0, "dry_run": True}

    token = _get_token()
    logger.info("[1] Token OK")

    # 获取现有记录
    existing = _get_records(token)
    logger.info("[2] Wiki 现有 %d 条记录", len(existing))

    # 构建 URL 索引
    existing_urls: set[str] = set()
    garbage: list[tuple[str, str]] = []  # (record_id, name)
    for r in existing:
        url_field = r.get("fields", {}).get("链接")
        name = r.get("fields", {}).get("项目名", "")
        if url_field and isinstance(url_field, dict) and url_field.get("link"):
            existing_urls.add(url_field["link"])
        elif not name or name == "" or name == "-":
            garbage.append((r["record_id"], name))

    # 清理垃圾记录
    cleaned = 0
    for rec_id, name in garbage:
        if dry_run:
            logger.info("[DRY] Would delete garbage record %s (%s)", rec_id, name)
        else:
            _delete_record(token, rec_id)
            logger.info("[CLEAN] Deleted: %s (%s)", rec_id, name)
            cleaned += 1

    # 过滤出需要新增的
    new_projects = [p for p in projects if p.get("url") not in existing_urls]
    logger.info("[3] 需要新增: %d, 已存在: %d", len(new_projects), len(existing_urls))

    created = 0
    skipped = 0
    for proj in new_projects:
        fields = {
            "项目名": proj.get("name", proj.get("repo", "")),
            "Stars": str(proj.get("stars", proj.get("stars_today", 0))),
            "语言": proj.get("lang", proj.get("language", "-")),
            "今日增长": proj.get("growth", proj.get("stars_today", "-")),
            "简介": proj.get("desc", proj.get("description", "")),
            "链接": {"link": proj.get("url", "")},
        }
        if dry_run:
            logger.info("[DRY] Would create: %s", fields["项目名"])
        else:
            _create_record(token, fields)
            logger.info("[NEW] %s (%s⭐)", fields["项目名"], fields["Stars"])
            created += 1

    logger.info("=== 完成 ===")
    logger.info("新增: %d, 跳过: %d, 清理: %d", created, skipped, cleaned)
    return {"created": created, "skipped": skipped, "cleaned": cleaned}
