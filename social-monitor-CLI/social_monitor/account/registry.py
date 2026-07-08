"""从 guide/监控渠道-账号.md 解析结构化账号清单"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

TABLE_ROW = re.compile(
    r"^\|\s*(?P<canonical>[^|]+?)\s*\|\s*(?P<platform>[^|]+?)\s*\|\s*(?P<display>[^|]+?)\s*\|\s*"
    r"(?P<account_id>[^|]+?)\s*\|\s*(?P<entity>[^|]+?)\s*\|\s*(?P<priority>[^|]+?)\s*\|\s*(?P<status>[^|]+?)\s*\|$"
)

PLATFORM_KEY = {
    "B站": "bilibili",
    "抖音": "douyin",
    "公众号": "wechat",
    "视频号": "channels",
    "微博": "weibo",
    "小红书": "xiaohongshu",
}


@dataclass
class AccountEntry:
    canonical_name: str
    platform: str
    platform_key: str
    display_name: str
    account_id: str
    entity_type: str
    priority: str
    status: str
    line_no: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def needs_resolve(self) -> bool:
        return self.status == "pending_id" and self.account_id in ("-", "")


def default_registry_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "guide" / "监控渠道-账号.md"


def load_registry(path: Optional[Path] = None) -> List[AccountEntry]:
    registry_path = path or default_registry_path()
    if not registry_path.exists():
        raise FileNotFoundError(f"账号清单不存在: {registry_path}")

    entries: List[AccountEntry] = []
    for line_no, line in enumerate(registry_path.read_text(encoding="utf-8").splitlines(), start=1):
        match = TABLE_ROW.match(line.strip())
        if not match:
            continue
        platform = match.group("platform").strip()
        canonical = match.group("canonical").strip()
        if canonical in ("canonical_name", "") or platform.startswith("-") or canonical.startswith("-"):
            continue
        entries.append(
            AccountEntry(
                canonical_name=canonical,
                platform=platform,
                platform_key=PLATFORM_KEY.get(platform, platform),
                display_name=match.group("display").strip(),
                account_id=match.group("account_id").strip(),
                entity_type=match.group("entity").strip(),
                priority=match.group("priority").strip(),
                status=match.group("status").strip(),
                line_no=line_no,
            )
        )
    return entries


def filter_entries(
    entries: List[AccountEntry],
    priority: Optional[str] = None,
    platform_key: Optional[str] = None,
    only_pending: bool = True,
) -> List[AccountEntry]:
    result = entries
    if priority:
        result = [e for e in result if e.priority == priority]
    if platform_key:
        result = [e for e in result if e.platform_key == platform_key]
    if only_pending:
        result = [e for e in result if e.needs_resolve]
    return result


def apply_resolved_ids(registry_path: Path, results: List[Dict[str, Any]]) -> int:
    """将 resolved 的 account_id 写回 markdown 表格"""
    lines = registry_path.read_text(encoding="utf-8").splitlines()
    updated = 0
    resolve_map = {
        r["line_no"]: r["account_id_resolved"]
        for r in results
        if r.get("resolved") and r.get("account_id_resolved")
    }

    for line_no, new_id in resolve_map.items():
        if line_no < 1 or line_no > len(lines):
            continue
        match = TABLE_ROW.match(lines[line_no - 1].strip())
        if not match:
            continue
        old = match.group("account_id").strip()
        if old not in ("-", ""):
            continue
        parts = [p.strip() for p in lines[line_no - 1].strip().strip("|").split("|")]
        if len(parts) >= 4:
            parts[3] = new_id
            lines[line_no - 1] = "| " + " | ".join(parts) + " |"
            updated += 1

    if updated:
        registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return updated
