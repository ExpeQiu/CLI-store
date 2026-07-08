import sys
import tempfile
from unittest.mock import MagicMock, patch

from social_monitor.storage.factory import get_storage
from social_monitor.storage.json_storage import JSONStorage


def test_json_storage_append():
    with tempfile.TemporaryDirectory() as tmp:
        storage = JSONStorage(data_dir=tmp)
        items = [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
        count = storage.save("weibo", "test", items, mode="replace")
        assert count == 2

        new_items = [{"id": "2", "title": "b"}, {"id": "3", "title": "c"}]
        count = storage.save("weibo", "test", new_items, mode="append")
        assert count == 3

        loaded = storage.load("weibo", "test")
        ids = {item["id"] for item in loaded}
        assert ids == {"1", "2", "3"}


def test_postgres_row_params_uses_word_as_content_id():
    from social_monitor.storage.postgres_storage import PostgresStorage

    params = PostgresStorage._row_params(
        "weibo",
        "trending",
        {"word": "测试热搜", "hot_value": 100},
    )
    assert params[2] == "测试热搜"
    assert params[3] == "测试热搜"
    assert params[6] == 100


@patch("social_monitor.storage.factory.load_config")
def test_get_storage_postgres(mock_load_config):
    mock_load_config.return_value = {
        "storage": {"type": "postgres"},
        "postgres": {"host": "localhost", "database": "test"},
    }
    mock_psycopg2 = MagicMock()
    mock_conn = MagicMock()
    mock_psycopg2.connect.return_value = mock_conn
    with patch.dict(sys.modules, {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
        storage, label = get_storage()
        assert label == "PostgreSQL"
        mock_psycopg2.connect.assert_called_once()


@patch("social_monitor.storage.factory.load_config")
def test_get_storage_json(mock_load_config):
    with tempfile.TemporaryDirectory() as tmp:
        mock_load_config.return_value = {
            "storage": {"type": "json", "data_dir": tmp},
        }
        storage, label = get_storage()
        assert label == "JSON"
        assert isinstance(storage, JSONStorage)
