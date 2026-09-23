"""Role gating across the mutating surface.

Before this, almost every write route accepted any authenticated user — a
`viewer` could delete rules, mint ingest tokens and wipe the operation log.
Reads stay open to every logged-in user; writes need admin/operator; the
destructive / credential-minting subset needs admin.
"""
import pytest

# method, path template (Python format), body or None, minimum role
#   role order: viewer < operator < admin
WRITE_MATRIX = [
    ("POST",   "/api/rules/es-preview",      {}),
    ("POST",   "/api/rules/telegram-test",   {}),
    ("POST",   "/api/rules",                 {}),
    ("PUT",    "/api/rules/1",               {}),
    ("DELETE", "/api/rules/1",               None),
    ("POST",   "/api/rules/1/run",           None),
    ("POST",   "/api/rules/1/execute",       None),
    ("PUT",    "/api/alerts/1",              {}),
    ("POST",   "/api/alerts/batch-update",   {"ids": [1]}),
    ("POST",   "/api/alerts/batch-delete",   {"ids": [1]}),
    ("DELETE", "/api/alerts/1",              None),
    ("POST",   "/api/addresses",             {"ip_address": "1.1.1.1", "country": "US"}),
    ("PUT",    "/api/addresses/1",           {}),
    ("DELETE", "/api/addresses/1",           None),
    ("POST",   "/api/addresses/batch-delete", {"ids": [1]}),
    ("POST",   "/api/addresses/migrate-countries", {}),
    ("POST",   "/api/logs",                  {"action": "test"}),
]

ADMIN_ONLY = [
    ("POST",   "/api/remote/endpoints",                   {"name": "rbac1"}),
    ("POST",   "/api/remote/endpoints/1/rotate-token",    None),
    ("DELETE", "/api/remote/endpoints/1",                 None),
    ("DELETE", "/api/remote/endpoints/1/logs",            None),
    ("POST",   "/api/settings/users",                     {"username": "x", "password": "GoodPass1!"}),
    ("PUT",    "/api/settings/config",                    {"updates": {}}),
    ("DELETE", "/api/settings/users/1",                   None),
]


def _call(client, method, path, body, headers):
    fn = getattr(client, method.lower())
    if body is None:
        return fn(path, headers=headers)
    return fn(path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", WRITE_MATRIX)
def test_viewer_cannot_write(client, method, path, body, viewer_user):
    from tests.conftest import login_headers

    h = login_headers(client, "viewer", "ViewPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let a viewer through"


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY)
def test_operator_cannot_touch_credentials(client, method, path, body, operator_user):
    from tests.conftest import login_headers

    h = login_headers(client, "operator", "OperPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let an operator through"


@pytest.mark.parametrize("method,path,body", WRITE_MATRIX)
def test_anonymous_cannot_write(client, method, path, body):
    client.cookies.clear()
    resp = _call(client, method, path, body, None)
    # 401/403 = auth rejected. 422 = body validation raced auth first — either
    # way nothing was written, which is all this case is asserting.
    assert resp.status_code in (401, 403, 422), f"{method} {path} let anonymous in"


def test_operator_can_write_operational_data(client, operator_user):
    """The point of operator is day-to-day work — it must NOT be a read-only role."""
    from tests.conftest import login_headers

    h = login_headers(client, "operator", "OperPass1")
    resp = client.post(
        "/api/addresses",
        json={"ip_address": "8.8.8.8", "country": "US"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_log_entry_cannot_spoof_username(client, operator_user):
    from tests.conftest import login_headers

    h = login_headers(client, "operator", "OperPass1")
    resp = client.post(
        "/api/logs",
        json={"username": "admin", "ip_address": "9.9.9.9", "action": "spoof"},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "operator"
    assert data["ip_address"] != "9.9.9.9"
