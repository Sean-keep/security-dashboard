"""角色权限矩阵的在线勾选分配。

矩阵不再是写死的常量 —— 系统管理员在权限管理页勾选分配，落 ``role_permissions``
表。这里钉住两件事：

1. 谁能勾（系统管理员 / 安全管理员），谁不能（操作员 / 只读 / 审计）。
2. 勾也踩不破三权分立的三条底线 —— 互斥、独占、必须有人接。

第 2 条比第 1 条重要：能改矩阵的人本来就是管理员，真正防的是「好心办坏事」——
把方便起见把审计也给系统管理员，三权分立当场变回一把抓。
"""


def _login(client, u, p):
    from tests.conftest import login_headers

    return login_headers(client, u, p)


def _get_matrix(client, headers):
    resp = client.get("/api/settings/permissions", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _matrix_as_payload(data):
    """GET 回的 roles 结构 → PUT 要的 {role: [perm, ...]}。"""
    return {
        r["role"]: [p["name"] for p in r["permissions"] if p["granted"]]
        for r in data["roles"]
    }


def _put_matrix(client, headers, roles):
    return client.put("/api/settings/permissions", json={"roles": roles}, headers=headers)


# ── 谁能勾 ─────────────────────────────────────────────────────────
def test_sys_admin_can_assign_matrix(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    # 随手把 manage_system 勾给 operator —— 不是三权，应当放行
    payload["operator"] = sorted(set(payload["operator"]) | {"manage_system"})
    resp = _put_matrix(client, h, payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 200

    after = _matrix_as_payload(_get_matrix(client, h))
    assert "manage_system" in after["operator"]


def test_sec_admin_can_assign_matrix(client, sec_admin_user):
    """安全管理员持「授权」那把钥匙，也能改岗位职责表。"""
    h = _login(client, "sec", "SecPass1!")
    payload = _matrix_as_payload(_get_matrix(client, h))
    payload["viewer"] = sorted(set(payload["viewer"]) | {"operate"})
    resp = _put_matrix(client, h, payload)
    assert resp.json()["code"] == 200


def test_operator_cannot_assign_matrix(client, operator_user, admin_user):
    hop = _login(client, "operator", "OperPass1")
    assert _put_matrix(client, hop, {"viewer": []}).status_code == 403


def test_viewer_cannot_assign_matrix(client, viewer_user, admin_user):
    hv = _login(client, "viewer", "ViewPass1")
    assert _put_matrix(client, hv, {"viewer": ["operate"]}).status_code == 403


def test_audit_admin_cannot_assign_matrix(client, audit_admin_user, admin_user):
    """审计管理员只看不改 —— 连自己的权限都不能自己加。"""
    ha = _login(client, "audit", "AuditPass1")
    assert _put_matrix(client, ha, {"audit_admin": ["audit", "operate"]}).status_code == 403


# ── 勾也踩不破的三条底线 ───────────────────────────────────────────
def test_cannot_stack_two_powers_on_one_role(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    # 系统管理员想顺手看审计 —— 这正是三权分立要挡的那一步
    payload["sys_admin"] = sorted(set(payload["sys_admin"]) | {"audit"})
    payload["audit_admin"] = []
    resp = _put_matrix(client, h, payload)
    assert resp.json()["code"] == 400
    assert "三权互斥" in resp.json()["msg"]

    # 没写进去
    after = _matrix_as_payload(_get_matrix(client, h))
    assert "audit" not in after["sys_admin"]
    assert "audit" in after["audit_admin"]


def test_cannot_drop_a_power_entirely(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    payload["audit_admin"] = []
    resp = _put_matrix(client, h, payload)
    assert resp.json()["code"] == 400
    assert "无人持有" in resp.json()["msg"]


def test_cannot_share_a_power_between_two_roles(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    payload["operator"] = sorted(set(payload["operator"]) | {"audit"})  # 审计配两把
    resp = _put_matrix(client, h, payload)
    assert resp.json()["code"] == 400
    assert "只能落在一个角色上" in resp.json()["msg"]


def test_cannot_add_unknown_role_or_permission(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))

    bad = dict(payload)
    bad["root"] = ["manage_accounts"]
    assert _put_matrix(client, h, bad).json()["code"] == 400

    bad = dict(payload)
    bad["operator"] = ["operate", "launch_missiles"]
    assert _put_matrix(client, h, bad).json()["code"] == 400


def test_power_can_move_between_roles(client, admin_user):
    """三权独占的意思是「只认一个在任者」，不是「钉死在某个角色上」。"""
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    # 把「授权」从安全管理员挪给业务操作员
    payload["sec_admin"] = [p for p in payload["sec_admin"] if p != "manage_authz"]
    payload["operator"] = sorted(set(payload["operator"]) | {"manage_authz"})
    resp = _put_matrix(client, h, payload)
    assert resp.json()["code"] == 200

    after = _matrix_as_payload(_get_matrix(client, h))
    assert "manage_authz" not in after["sec_admin"]
    assert "manage_authz" in after["operator"]


# ── 改完立刻生效 ───────────────────────────────────────────────────
def test_matrix_change_applies_to_next_request(client, admin_user, operator_user):
    """勾完不用重启：require_permission 每次请求都读一遍矩阵。"""
    h = _login(client, "admin", "AdminPass1")
    hop = _login(client, "operator", "OperPass1")

    # 先确认 operator 能干活（写操作日志 = operate）
    assert client.post("/api/logs", json={"action": "probe"}, headers=hop).status_code != 403

    payload = _matrix_as_payload(_get_matrix(client, h))
    payload["operator"] = [p for p in payload["operator"] if p != "operate"]
    assert _put_matrix(client, h, payload).json()["code"] == 200

    # 下一次请求就被挡下来
    resp = client.post("/api/logs", json={"action": "probe"}, headers=hop)
    assert resp.status_code == 403

    # /me 也跟着变 —— 前端的按钮显隐靠它
    me = client.get("/api/auth/me", headers=hop).json()["data"]
    assert "operate" not in me["permissions"]


def test_matrix_change_reaches_me_for_everyone(client, admin_user, sec_admin_user):
    ha = _login(client, "admin", "AdminPass1")
    hs = _login(client, "sec", "SecPass1!")

    payload = _matrix_as_payload(_get_matrix(client, ha))
    payload["sec_admin"] = [p for p in payload["sec_admin"] if p != "operate"]
    assert _put_matrix(client, ha, payload).json()["code"] == 200

    me = client.get("/api/auth/me", headers=hs).json()["data"]
    assert "operate" not in me["permissions"]
    assert "manage_authz" in me["permissions"]


# ── 读接口的自述 ───────────────────────────────────────────────────
def test_matrix_endpoint_tells_me_whether_i_can_assign(client, admin_user, operator_user):
    h = _login(client, "admin", "AdminPass1")
    data = _get_matrix(client, h)
    assert data["can_assign"] is True
    assert set(data["defaults"]) == set(data["role_labels"])
    assert "manage_accounts" in data["defaults"]["sys_admin"]

    hop = _login(client, "operator", "OperPass1")
    assert _get_matrix(client, hop)["can_assign"] is False


def test_defaults_match_the_documented_matrix(client, admin_user):
    """GET 回的 defaults 必须和 ROLE_PERMISSIONS 一致 —— 「恢复默认」按钮的权威来源。"""
    from app.core.permissions import ROLE_PERMISSIONS

    h = _login(client, "admin", "AdminPass1")
    defaults = _get_matrix(client, h)["defaults"]
    assert {r: set(v) for r, v in defaults.items()} == {
        r: set(v) for r, v in ROLE_PERMISSIONS.items()
    }


def test_restore_defaults_is_just_a_normal_save(client, admin_user):
    """「恢复默认」前端就是拿 defaults 重填再保存，所以后端没有单独开关。"""
    h = _login(client, "admin", "AdminPass1")
    payload = _matrix_as_payload(_get_matrix(client, h))
    payload["viewer"] = ["operate"]
    assert _put_matrix(client, h, payload).json()["code"] == 200

    defaults = _get_matrix(client, h)["defaults"]
    assert _put_matrix(client, h, defaults).json()["code"] == 200
    after = _matrix_as_payload(_get_matrix(client, h))
    assert after["viewer"] == []
