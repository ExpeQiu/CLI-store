"""Web API smoke 测试。"""

from fastapi.testclient import TestClient

from video_edit.web.server import create_app


def test_ping_and_demo_job():
    app = create_app()
    client = TestClient(app)
    ping = client.get("/api/ping")
    assert ping.status_code == 200
    assert ping.json().get("ok") is True

    resp = client.post("/api/aroll/run", data={"demo": "true"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    import time

    for _ in range(30):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job.get("status") == "completed":
            break
        if job.get("status") == "failed":
            raise AssertionError(job.get("error"))
        time.sleep(0.2)
    else:
        raise AssertionError("demo job timeout")

    assert job["result"]["fcpxml"]
