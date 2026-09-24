"""System-config secrets must never leave the server, and unknown keys must fail loudly.

`GET /settings/config` used to hand back every SystemConfig value verbatim —
including `es_password` / `mysql_password` / `grafana_api_key` — to any logged-in
user, while the UI painted `********` over them. That made the mask decorative.

`PUT /settings/config` used to `continue` on unknown keys, so an admin tightening
`login_max_attempts` saw "保存成功" while `saved=0` and the runtime kept the env
default. Silent policy failure.
"""
from tests.conftest import login_headers

SECRET_KEYS = ("es_password", "mysql_password", "grafana_api_key", "grafana_password")
PLAIN_KEYS = ("es_host", "es_index", "login_max_attempts")


def _seed(db):
    """Insert known rows into the test engine — we need a known secret to prove it's hidden."""
    from app.models.config import SystemConfig

    for key, val in [
        ("es_host", "es.internal"),
        ("es_index", "security-logs-*"),
        ("es_password", "SuperSecretES!"),
        ("mysql_password", "SuperSecretMySQL!"),
        ("grafana_api_key", "glsa_SuperSecret"),
        ("login_max_attempts", "5"),
    ]:
        row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if row is None:
            db.add(SystemConfig(key=key, value=val, label=key, group_name="test"))
        else:
            row.value = val
    db.commit()


def _config(client, headers):
    resp = client.get("/api/settings/config", headers=headers)
    assert resp.status_code == 200
    groups = resp.json()["data"]
    flat = {}
    for rows in groups.values():
        for row in rows:
            flat[row["key"]] = row
    return flat


def _raw_value(db, key: str) -> str:
    from app.models.config import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row else ""


def test_config_never_returns_secret_values(client, db_session):
    h = login_headers(client)
    _seed(db_session)
    flat = _config(client, h)

    for key in SECRET_KEYS:
        if key not in flat:
            continue
        row = flat[key]
        assert row["value"] == "", f"{key} must not be echoed back"
        assert row["secret_set"] is True

    for key in PLAIN_KEYS:
        row = flat[key]
        assert row["value"] != ""
        assert not row.get("secret_set")


def test_blank_secret_keeps_existing_value(client, db_session):
    h = login_headers(client)
    _seed(db_session)
    resp = client.put(
        "/api/settings/config",
        json={"updates": {"es_host": "es2.internal", "es_password": ""}},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
    assert "es_password" in resp.json()["data"]["kept"]

    flat = _config(client, h)
    assert flat["es_host"]["value"] == "es2.internal"
    assert flat["es_password"]["value"] == ""
    assert flat["es_password"]["secret_set"] is True
    assert _raw_value(db_session, "es_password") == "SuperSecretES!"


def test_secret_can_be_rotated_with_new_value(client, db_session):
    h = login_headers(client)
    _seed(db_session)
    resp = client.put(
        "/api/settings/config",
        json={"updates": {"es_password": "Rotated!"}},
        headers=h,
    )
    assert resp.json()["code"] == 200
    assert _raw_value(db_session, "es_password") == "Rotated!"


def test_unknown_keys_rejected_loudly(client, db_session):
    h = login_headers(client)
    _seed(db_session)
    resp = client.put(
        "/api/settings/config",
        json={"updates": {"login_max_attempts": "3", "totally_not_a_key": "1"}},
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "totally_not_a_key" in body["msg"]
    # The valid half of the batch must not have been applied.
    assert _raw_value(db_session, "login_max_attempts") == "5"


def test_es_default_hides_password(client, db_session):
    h = login_headers(client)
    _seed(db_session)
    resp = client.get("/api/settings/es-default", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["password"] == ""
    assert data["password_set"] is True


def test_user_list_needs_account_or_authz(client, operator_user):
    op = login_headers(client, "operator", "OperPass1")
    assert client.get("/api/settings/users", headers=op).status_code == 403

    admin = login_headers(client)
    assert client.get("/api/settings/users", headers=admin).status_code == 200


def test_role_must_be_known(client, db_session):
    h = login_headers(client)
    resp = client.post(
        "/api/settings/users",
        json={"username": "intruder", "password": "GoodPass1!", "role": "superadmin"},
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_login_logs_are_audit_only(client, operator_user):
    op = login_headers(client, "operator", "OperPass1")
    assert client.get("/api/settings/login-logs", headers=op).status_code == 403
