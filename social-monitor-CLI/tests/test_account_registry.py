"""账号 registry 与 matcher 单元测试"""

from pathlib import Path

import pytest

from social_monitor.account.matcher import normalize_name, pick_best_candidate, score_name_match
from social_monitor.account.registry import (
    AccountEntry,
    apply_resolved_ids,
    filter_entries,
    load_registry,
)
from social_monitor.account.resolvers import build_monitor_yaml_snippet, resolve_entry


SAMPLE_MD = """\
# 测试

| canonical_name | platform | display_name | account_id | entity_type | priority | status |
|----------------|----------|--------------|------------|-------------|----------|--------|
| 长城技术中心 | B站 | 长城技术中心 | - | official | P0 | pending_id |
| 长城技术中心 | 抖音 | 长城技术中心 | MS4w | official | P0 | ready |
| TeslaAI | B站 | TeslaAI | - | official | P0 | pending_id |
| 长城技术中心 | 视频号 | 长城技术中心 | - | official | P0 | unsupported |
"""


@pytest.fixture
def sample_registry(tmp_path: Path) -> Path:
    path = tmp_path / "accounts.md"
    path.write_text(SAMPLE_MD, encoding="utf-8")
    return path


def test_load_registry(sample_registry: Path):
    entries = load_registry(sample_registry)
    assert len(entries) == 4
    assert entries[0].canonical_name == "长城技术中心"
    assert entries[0].platform_key == "bilibili"
    assert entries[0].needs_resolve is True
    assert entries[1].needs_resolve is False


def test_filter_p0_pending(sample_registry: Path):
    entries = load_registry(sample_registry)
    pending = filter_entries(entries, priority="P0", only_pending=True)
    assert len(pending) == 2
    names = {e.display_name for e in pending}
    assert names == {"长城技术中心", "TeslaAI"}


def test_normalize_and_score():
    assert normalize_name("XP-何小鹏") == normalize_name("xp何小鹏")
    assert score_name_match("长城技术中心", "长城技术中心") == 1.0
    assert score_name_match("Nicole吴会肖", "长城汽车吴会肖") >= 0.82


def test_pick_best_candidate_ambiguous():
    candidates = [
        {"account_id": "1", "name": "吉利Tech"},
        {"account_id": "2", "name": "吉利 TECH"},
    ]
    best, scored = pick_best_candidate("吉利Tech", candidates)
    assert best is not None
    assert best["account_id"] == "1"
    assert len(scored) == 2


def test_apply_resolved_ids(sample_registry: Path):
    entries = load_registry(sample_registry)
    target = next(e for e in entries if e.display_name == "长城技术中心" and e.platform == "B站")
    results = [
        {
            "line_no": target.line_no,
            "resolved": True,
            "account_id_resolved": "614946423",
        }
    ]
    count = apply_resolved_ids(sample_registry, results)
    assert count == 1
    updated = load_registry(sample_registry)
    bilibili = [e for e in updated if e.platform == "B站"][0]
    assert bilibili.account_id == "614946423"


def test_build_monitor_yaml_snippet():
    results = [
        {
            "resolved": True,
            "resolve_status": "resolved",
            "platform_key": "bilibili",
            "account_id_resolved": "123",
            "canonical_name": "TeslaAI",
        },
        {
            "resolved": True,
            "resolve_status": "resolved",
            "platform_key": "douyin",
            "account_id_resolved": "MS4wLjAB",
            "canonical_name": "TeslaAI",
        },
    ]
    text = build_monitor_yaml_snippet(results)
    assert "uid: 123" in text
    assert "sec_uid: MS4wLjAB" in text


def test_resolve_entry_unsupported_platform():
    entry = AccountEntry(
        canonical_name="长城技术中心",
        platform="视频号",
        platform_key="channels",
        display_name="长城技术中心",
        account_id="-",
        entity_type="official",
        priority="P0",
        status="unsupported",
    )
    result = resolve_entry(entry)
    assert result["resolve_status"] == "unsupported_platform"


def test_load_project_registry():
    path = Path(__file__).resolve().parent.parent / "guide" / "监控渠道-账号.md"
    if not path.exists():
        pytest.skip("guide/监控渠道-账号.md 不存在")
    entries = filter_entries(load_registry(path), priority="P0", only_pending=True)
    assert len(entries) >= 15
    platforms = {e.platform_key for e in entries}
    assert "bilibili" in platforms
    assert "channels" not in platforms


def test_platforms_needing_login(monkeypatch):
    from social_monitor.account.auth import platforms_needing_login

    entries = [
        AccountEntry(
            canonical_name="T",
            platform="抖音",
            platform_key="douyin",
            display_name="T",
            account_id="-",
            entity_type="official",
            priority="P0",
            status="pending_id",
        )
    ]
    monkeypatch.setattr("social_monitor.account.auth.get_cookie", lambda _p: None)
    monkeypatch.setattr("social_monitor.account.auth.has_browser_session", lambda _p: False)
    assert platforms_needing_login(entries) == {"douyin"}


def test_ensure_login_skips_when_ready(monkeypatch):
    from social_monitor.account.auth import ensure_login_for_entries

    entries = [
        AccountEntry(
            canonical_name="T",
            platform="抖音",
            platform_key="douyin",
            display_name="T",
            account_id="-",
            entity_type="official",
            priority="P0",
            status="pending_id",
        )
    ]
    monkeypatch.setattr(
        "social_monitor.account.auth.platform_auth_ready",
        lambda _p: True,
    )
    assert ensure_login_for_entries(entries, interactive=False) == []
