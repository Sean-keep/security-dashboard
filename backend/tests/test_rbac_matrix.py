"""Role gating across the mutating surface (三权分立).

Before any of this, almost every write route accepted any authenticated user —
a `viewer` could delete rules, mint ingest tokens and wipe the operation log.
Then the model was `admin/operator/viewer`, where `admin` held 账号 + 授权 + 审计
in one hand. Now:

    权限点            sys_admin   sec_admin   audit_admin   operator   viewer
    manage_accounts   ✅           —            —             —          —
    manage_authz      —            ✅            —             —          —
    audit             —            —            ✅             —          —
    manage_system     ✅           —            —             —          —
    operate           ✅           ✅            —             ✅          —

Reads stay open to every logged-in user (审计管理员 needs to see the system to
make sense of its logs); writes need `operate`; the governing powers are split.
"""
import pytest

# method, path template, body or None, required permission
OPERATE_MATRIX = [
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

# 账号管理（系统管理员）—— 含改资料/删除/建号；改角色单独测
ACCOUNT_MATRIX = [
    ("POST",   "/api/settings/users",        {"username": "x", "password": "GoodPass1!"}),
    ("DELETE", "/api/settings/users/2",      None),
]

# 系统配置 / 远程接口 / 脚本库 / 任意代码执行（系统管理员）
SYSTEM_MATRIX = [
    ("PUT",    "/api/settings/config",       {"updates": {}}),
    ("POST",   "/api/remote/endpoints",      {"name": "rbac1"}),
    ("POST",   "/api/remote/endpoints/1/rotate-token", None),
    ("DELETE", "/api/remote/endpoints/1",    None),
    ("DELETE", "/api/remote/endpoints/1/logs", None),
    ("POST",   "/api/inspect/execute",       {"type": "python", "script": "print(1)"}),
    ("POST",   "/api/inspect/pip-install",   {"package": "requests"}),
    ("POST",   "/api/inspect/scripts",       {"name": "s", "type": "python", "content": "print(1)"}),
]

# 审计（审计管理员独占）
AUDIT_MATRIX = [
    ("GET", "/api/logs",            None),
    ("GET", "/api/settings/login-logs", None),
]

# 授权（安全管理员）—— 角色变更
AUTHZ_MATRIX = [
    ("PUT", "/api/settings/users/2/role", {"role": "viewer"}),
]


def _call(client, method, path, body, headers):
    fn = getattr(client, method.lower())
    if body is None:
        return fn(path, headers=headers)
    return fn(path, json=body, headers=headers)


def _login(client, username, password):
    from tests.conftest import login_headers

    return login_headers(client, username, password)


# ── 无特权角色：什么都写不了 ────────────────────────────────────────
@pytest.mark.parametrize("method,path,body", OPERATE_MATRIX + ACCOUNT_MATRIX + SYSTEM_MATRIX + AUTHZ_MATRIX)
def test_viewer_cannot_write(client, method, path, body, viewer_user):
    h = _login(client, "viewer", "ViewPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let a viewer through"


@pytest.mark.parametrize("method,path,body", ACCOUNT_MATRIX + SYSTEM_MATRIX + AUTHZ_MATRIX + AUDIT_MATRIX)
def test_operator_has_no_governing_power(client, method, path, body, operator_user):
    """操作员能干活，但碰不到账号 / 授权 / 系统配置 / 审计 —— 这正是分权的意义。"""
    h = _login(client, "operator", "OperPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let an operator through"


@pytest.mark.parametrize("method,path,body", OPERATE_MATRIX + ACCOUNT_MATRIX + SYSTEM_MATRIX + AUTHZ_MATRIX)
def test_anonymous_cannot_write(client, method, path, body):
    client.cookies.clear()
    resp = _call(client, method, path, body, None)
    # 401/403 = auth rejected. 422 = body validation raced auth first — either
    # way nothing was written, which is all this case is asserting.
    assert resp.status_code in (401, 403, 422), f"{method} {path} let anonymous in"


# ── 三权互斥：谁也摸不到别人的钥匙 ──────────────────────────────────
@pytest.mark.parametrize("method,path,body", AUTHZ_MATRIX + AUDIT_MATRIX)
def test_sys_admin_holds_accounts_but_not_authz_or_audit(client, method, path, body, admin_user, db_session):
    """系统管理员能建号、能配系统，但不能改角色（授权），也看不到审计。"""
    # 需要目标用户存在，否则可能命中 404 而不是 403 —— 这里只关心鉴权。
    from app.api.security import get_password_hash
    from app.models.user import User

    if not db_session.query(User).filter(User.username == "target").first():
        db_session.add(User(
            username="target",
            password_hash=get_password_hash("TargetPass1"),
            nickname="T",
            role="operator",
            is_active=True,
        ))
        db_session.commit()

    h = _login(client, "admin", "AdminPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let 系统管理员 touch a foreign power"


@pytest.mark.parametrize("method,path,body", ACCOUNT_MATRIX + AUDIT_MATRIX + SYSTEM_MATRIX)
def test_sec_admin_holds_authz_but_not_accounts_or_audit(client, method, path, body, sec_admin_user, db_session):
    from app.api.security import get_password_hash
    from app.models.user import User

    if not db_session.query(User).filter(User.username == "target").first():
        db_session.add(User(
            username="target",
            password_hash=get_password_hash("TargetPass1"),
            nickname="T",
            role="operator",
            is_active=True,
        ))
        db_session.commit()

    h = _login(client, "sec", "SecPass1!")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let 安全管理员 touch a foreign power"


@pytest.mark.parametrize("method,path,body", ACCOUNT_MATRIX + AUTHZ_MATRIX + SYSTEM_MATRIX + OPERATE_MATRIX)
def test_audit_admin_cannot_change_anything(client, method, path, body, audit_admin_user):
    """审计管理员是只读的 —— 连日常业务都做不了，更碰不到账号与授权。"""
    h = _login(client, "audit", "AuditPass1")
    resp = _call(client, method, path, body, h)
    assert resp.status_code == 403, f"{method} {path} let 审计管理员 write"


# ── 各自的钥匙确实能用 ──────────────────────────────────────────────
def test_sys_admin_can_do_daily_work(client, admin_user):
    """系统管理员带 operate —— 平台主要写报告，不能把建号的人挡在日报外面。"""
    h = _login(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/addresses",
        json={"ip_address": "8.8.8.8", "country": "US"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_sec_admin_can_do_daily_work(client, sec_admin_user):
    h = _login(client, "sec", "SecPass1!")
    resp = client.post(
        "/api/addresses",
        json={"ip_address": "8.8.4.4", "country": "US"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_operator_can_write_operational_data(client, operator_user):
    """The point of operator is day-to-day work — it must NOT be a read-only role."""
    h = _login(client, "operator", "OperPass1")
    resp = client.post(
        "/api/addresses",
        json={"ip_address": "1.0.53.0", "country": "US"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_audit_admin_can_read_audit(client, audit_admin_user, operator_user):
    """审计管理员看得见审计日志 —— 这是三权里属于他的那一件。"""
    hop = _login(client, "operator", "OperPass1")
    client.post("/api/logs", json={"action": "audit-fixture"}, headers=hop)

    h = _login(client, "audit", "AuditPass1")
    assert client.get("/api/logs", headers=h).status_code == 200
    assert client.get("/api/settings/login-logs", headers=h).status_code == 200


def test_sys_admin_cannot_read_audit(client, admin_user):
    """分权的另一半：建号的人看不见登录日志。"""
    h = _login(client, "admin", "AdminPass1")
    assert client.get("/api/settings/login-logs", headers=h).status_code == 403
    assert client.get("/api/logs", headers=h).status_code == 403


def test_log_entry_cannot_spoof_username(client, operator_user):
    h = _login(client, "operator", "OperPass1")
    resp = client.post(
        "/api/logs",
        json={"username": "admin", "ip_address": "9.9.9.9", "action": "spoof"},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "operator"
    assert data["ip_address"] != "9.9.9.9"
