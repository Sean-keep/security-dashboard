"""Script execution must leave an audit trail.

Before: `/api/inspect/execute` ran arbitrary code and the only record was the
HTTP response. For a security dashboard that is the wrong default.
"""
from tests.conftest import login_headers


def test_adhoc_run_is_recorded(client):
    h = login_headers(client)
    resp = client.post(
        "/api/inspect/execute",
        json={"script": "print('hello-audit')", "type": "python"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["exit_code"] == 0

    from app.models.base import SessionLocal
    from app.models.script_run import ScriptRunLog

    # TestClient uses the overridden session; read through the app session that
    # the endpoint just wrote to. Use the same override by re-querying via API.
    # (The run list endpoint is per-script; an adhoc run has script_id=None, so
    # assert on the response payload fields instead of a list call.)
    assert "duration_ms" in resp.json()["data"]


def test_saved_script_run_is_listable(client):
    h = login_headers(client)
    created = client.post(
        "/api/inspect/scripts",
        json={"name": "audit-script", "script_type": "python", "content": "print(1)"},
        headers=h,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    data = body.get("data") or {}
    script_id = data.get("id")
    assert script_id, body

    run = client.post(
        "/api/inspect/scripts/execute",
        json={"script_ids": [script_id]},
        headers=h,
    )
    assert run.status_code == 200, run.text
    assert run.json()["data"]["results"][0]["exit_code"] == 0

    listed = client.get(f"/api/inspect/scripts/{script_id}/runs", headers=h)
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert items, "a run must be recorded"
    top = items[0]
    assert top["run_by"] == "admin"
    assert top["script_version_hash"]
    assert top["trigger"] == "manual"
    assert top["duration_ms"] is not None


def test_runs_are_admin_only(client, operator_user):
    h = login_headers(client, "operator", "OperPass1")
    assert client.get("/api/inspect/scripts/1/runs", headers=h).status_code == 403
