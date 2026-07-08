"""微博热搜按日归档测试"""

from datetime import date
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from social_monitor.cli import cli


def test_weibo_trending_date_account_id():
    runner = CliRunner()
    sample = [{"rank": 1, "word": "测试", "hot_value": 100}]

    with patch("social_monitor.cli.WeiboCollector") as cls:
        inst = MagicMock()
        inst.fetch_trending.return_value = sample
        inst.__enter__ = MagicMock(return_value=inst)
        inst.__exit__ = MagicMock(return_value=False)
        cls.return_value = inst

        with patch("social_monitor.cli.get_storage") as gs:
            storage = MagicMock()
            gs.return_value = (storage, "PostgreSQL")

            result = runner.invoke(
                cli,
                ["fetch", "weibo-trending", "--date", "2026-06-23", "--save", "--count", "5"],
            )

    assert result.exit_code == 0
    storage.save.assert_called_once()
    args = storage.save.call_args[0]
    assert args[0] == "weibo"
    assert args[1] == "trending_2026-06-23"
    saved = args[2]
    assert saved[0]["snapshot_date"] == "2026-06-23"


def test_weibo_trending_default_date_today():
    runner = CliRunner()
    today = date.today().isoformat()
    sample = [{"rank": 1, "word": "今日", "hot_value": 1}]

    with patch("social_monitor.cli.WeiboCollector") as cls:
        inst = MagicMock()
        inst.fetch_trending.return_value = sample
        inst.__enter__ = MagicMock(return_value=inst)
        inst.__exit__ = MagicMock(return_value=False)
        cls.return_value = inst

        with patch("social_monitor.cli.get_storage") as gs:
            storage = MagicMock()
            gs.return_value = (storage, "PostgreSQL")
            result = runner.invoke(cli, ["fetch", "weibo-trending", "--save"])

    assert result.exit_code == 0
    assert storage.save.call_args[0][1] == f"trending_{today}"
