"""Web API 端点单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from comfyui.web.server import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_api_ping(client: TestClient) -> None:
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_api_workflow_not_found(client: TestClient) -> None:
    resp = client.get("/api/workflows/nonexistent_workflow_xyz")
    assert resp.status_code == 404


@patch("comfyui.web.server._start_job_thread")
def test_api_run_returns_job_id(mock_start: MagicMock, client: TestClient) -> None:
    mock_start.return_value = None
    resp = client.post(
        "/api/run",
        json={"workflow": "wan2.1_txt2img", "params": {"positive_prompt": "test"}, "profile": "fast"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    mock_start.assert_called_once()


@patch("comfyui.web.server._start_job_thread")
def test_api_image_i2i_returns_job_id(mock_start: MagicMock, client: TestClient) -> None:
    mock_start.return_value = None
    resp = client.post(
        "/api/image/i2i",
        data={"prompt": "styled portrait"},
        files={"image": ("test.png", b"fakepng", "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "job_id" in data
