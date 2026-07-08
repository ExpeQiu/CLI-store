"""CLI demo 模式与 JSON 契约测试"""

import json

from click.testing import CliRunner

from invest.cli import cli

runner = CliRunner()


def test_market_score_demo_json():
    result = runner.invoke(cli, ["market", "score", "--demo", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["module"] == "market-score"
    assert data["data_source"] == "demo"
    assert "total" in data


def test_account_status_demo_json():
    result = runner.invoke(cli, ["account", "status", "--demo", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["module"] == "account-status"
    assert data["account"]["total_asset"] > 0
