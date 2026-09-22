"""Response envelope + health + scheduler status contract."""
from tests.conftest import login_headers


def test_health_reports_database(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"


def test_scheduler_status_requires_auth(client):
    client.cookies.clear()
    resp = client.get("/api/scheduler/status")
    assert resp.status_code == 401


def test_scheduler_status_shape(client):
    headers = login_headers(client)
    resp = client.get("/api/scheduler/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert "running" in body["data"]
    assert "jobs" in body["data"]
    assert isinstance(body["data"]["jobs"], list)


def test_me_envelope_uses_code_200(client):
    headers = login_headers(client)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.json()["code"] == 200


def test_password_policy_message_is_chinese_and_specific(client):
    headers = login_headers(client)
    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "AdminPass1", "new_password": "abc"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "长度" in resp.text  # 具体的中文策略报错，不是裸 422
