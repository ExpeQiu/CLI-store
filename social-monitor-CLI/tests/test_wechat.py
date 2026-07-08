import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from social_monitor.cli import cli
from social_monitor.platforms.wechat import WeChatCollector

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>测试公众号</title>
    <item>
      <title>测试文章标题</title>
      <link>https://mp.weixin.qq.com/s/test123</link>
      <description><![CDATA[<p>这是摘要</p>]]></description>
      <pubDate>Mon, 16 Jun 2026 10:00:00 GMT</pubDate>
      <author>测试号</author>
      <guid>test-article-1</guid>
    </item>
  </channel>
</rss>
"""


class MockRSSHubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/wechat/mp/profile/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.end_headers()
            self.wfile.write(RSS_XML.encode("utf-8"))
            return
        if self.path.startswith("/wechat/feed/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.end_headers()
            self.wfile.write(RSS_XML.encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_rsshub_url():
    server = HTTPServer(("127.0.0.1", 0), MockRSSHubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_clean_html():
    assert WeChatCollector._clean_html("<p>hello</p>") == "hello"


def test_fetch_via_rsshub_primary_route(mock_rsshub_url):
    with WeChatCollector(rsshub_url=mock_rsshub_url) as collector:
        articles = collector.fetch_via_rsshub("test_wxid")

    assert len(articles) == 1
    assert articles[0]["title"] == "测试文章标题"
    assert articles[0]["url"] == "https://mp.weixin.qq.com/s/test123"
    assert articles[0]["summary"] == "这是摘要"
    assert articles[0]["author"] == "测试号"
    assert articles[0]["id"] == "test-article-1"


def test_fetch_via_rsshub_fallback_route():
    mock_resp = MagicMock()
    mock_resp.text = RSS_XML

    collector = WeChatCollector(rsshub_url="http://mock-rsshub")
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/wechat/mp/profile/demo"):
            raise ConnectionError("primary route failed")
        return mock_resp

    with patch.object(collector.http_client, "get", side_effect=fake_get):
        articles = collector.fetch_via_rsshub("demo")

    assert len(articles) == 1
    assert articles[0]["title"] == "测试文章标题"
    assert calls[0].endswith("/wechat/mp/profile/demo")
    assert calls[1].endswith("/wechat/feed/demo")


def test_fetch_via_rsshub_both_routes_fail():
    collector = WeChatCollector(rsshub_url="http://mock-rsshub")

    def fake_get(url, **kwargs):
        raise ConnectionError(f"unreachable: {url}")

    with patch.object(collector.http_client, "get", side_effect=fake_get):
        with pytest.raises(RuntimeError, match="主备路由均失败"):
            collector.fetch_via_rsshub("demo")
    collector.close()


def test_cli_fetch_wechat_rsshub_down():
    with patch.object(
        WeChatCollector,
        "fetch_via_rsshub",
        side_effect=RuntimeError("RSSHub 不可用 (http://mock-rsshub)，主备路由均失败。"),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "wechat", "--wxid", "demo", "--rsshub-url", "http://mock-rsshub"])

    assert result.exit_code != 0
    assert "RSSHub 不可用" in result.output
    assert "Traceback" not in result.output


def test_cli_fetch_wechat(mock_rsshub_url):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "fetch",
            "wechat",
            "--wxid",
            "test_wxid",
            "--rsshub-url",
            mock_rsshub_url,
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["title"] == "测试文章标题"


def test_config_check_wechat_ok(mock_rsshub_url):
    from social_monitor.utils.cookie_checker import check_platform

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("social_monitor.config.get_rsshub_url", return_value=mock_rsshub_url):
        with patch("social_monitor.utils.cookie_checker.HttpClient") as client_cls:
            client = client_cls.return_value
            client.get.return_value = mock_resp
            result = check_platform("wechat")

    assert result.ok is True
    assert result.platform == "wechat"
    assert "RSSHub 可达" in result.message
