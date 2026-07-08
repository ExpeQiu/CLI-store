"""监控编排测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from social_monitor.cli import cli
from social_monitor.monitor.runner import MonitorRunner


def test_monitor_run_dry_run(tmp_path, monkeypatch):
    monitor_file = tmp_path / "monitor.yaml"
    monitor_file.write_text(
        yaml.dump(
            {
                "weibo": {"accounts": ["123"], "trending": {"enabled": True}},
                "wechat": {"accounts": []},
                "bilibili": {"accounts": []},
                "douyin": {"accounts": []},
                "xiaohongshu": {"topics": ["测试"]},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "social_monitor.monitor.runner.load_monitor_config",
        lambda path=None: yaml.safe_load(monitor_file.read_text(encoding="utf-8")),
    )

    runner = MonitorRunner(dry_run=True, safe_mode=True, notify=False)
    summary = runner.run_daily()
    tasks = [t["task"] for t in summary["tasks"]]
    assert any("weibo:trending" in t for t in tasks)
    assert any("weibo:user:123" in t for t in tasks)
    assert any("xhs:topic:测试" in t for t in tasks)


def test_monitor_cli_dry_run(tmp_path, monkeypatch):
    runner = CliRunner()
    monitor_file = tmp_path / "monitor.yaml"
    monitor_file.write_text("weibo:\n  accounts: []\n", encoding="utf-8")
    monkeypatch.setattr(
        "social_monitor.utils.cookie_manager.MONITOR_FILE",
        monitor_file,
    )
    with patch("social_monitor.monitor.runner.run_monitor_task") as run:
        run.return_value = {"tasks": [], "errors": []}
        result = runner.invoke(cli, ["monitor", "run", "--dry-run"])
    assert result.exit_code == 0
    run.assert_called_once()
