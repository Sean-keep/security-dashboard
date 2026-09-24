"""用户管理：账号钥匙与授权钥匙分开，外加锁死护栏。

三权分立在用户管理上落成两条接口：
  POST/PUT/DELETE /settings/users           → manage_accounts（系统管理员）
  PUT /settings/users/{id}/role             → manage_authz   （安全管理员）
旧的 PUT /users 一条接口既改昵称又改角色，等于把两把钥匙焊在一起，所以拆开。
"""


def _login(client, u, p):
    from tests.conftest import login_headers

    return login_headers(client, u, p)


def test_create_user_honours_initial_role(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/settings/users",
        json={"username": "newbie", "password": "GoodPass1!", "role": "operator"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_create_user_rejects_unknown_role(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/settings/users",
        json={"username": "nope", "password": "GoodPass1!", "role": "superadmin"},
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_profile_update_ignores_role_field(client, admin_user, db_session):
    """改资料的接口不接受 role —— 那是授权钥匙的活。

    旧接口把 role 放在 UserUpdate 里，任何能改昵称的人都能给自己升权。
    现在即使客户端把 role 塞进 body 也改不动。
    """
    from app.models.user import User

    target = User(username="u1", password_hash="x", nickname="U1", role="viewer", is_active=True)
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    h = _login(client, "admin", "AdminPass1")
    resp = client.put(
        f"/api/settings/users/{target.id}",
        json={"nickname": "改过了", "role": "sys_admin"},
        headers=h,
    )
    assert resp.status_code == 200
    db_session.refresh(target)
    assert target.role == "viewer", "改资料接口偷偷把角色改了"
    assert target.nickname == "改过了"


def test_role_change_is_sec_admin_only(client, admin_user, sec_admin_user, operator_user, db_session):
    from app.models.user import User

    target = db_session.query(User).filter(User.username == "operator").one()
    tid = target.id

    # 系统管理员：403
    h = _login(client, "admin", "AdminPass1")
    assert client.put(
        f"/api/settings/users/{tid}/role", json={"role": "viewer"}, headers=h
    ).status_code == 403

    # 操作员：403
    hop = _login(client, "operator", "OperPass1")
    assert client.put(
        f"/api/settings/users/{tid}/role", json={"role": "viewer"}, headers=hop
    ).status_code == 403

    # 安全管理员：200，角色真的变了
    hs = _login(client, "sec", "SecPass1!")
    resp = client.put(f"/api/settings/users/{tid}/role", json={"role": "viewer"}, headers=hs)
    assert resp.status_code == 200
    db_session.refresh(target)
    assert target.role == "viewer"


def test_cannot_change_own_role(client, sec_admin_user, db_session):
    from app.models.user import User

    me = db_session.query(User).filter(User.username == "sec").one()
    h = _login(client, "sec", "SecPass1!")
    resp = client.put(f"/api/settings/users/{me.id}/role", json={"role": "audit_admin"}, headers=h)
    assert resp.json()["code"] == 400

    db_session.refresh(me)
    assert me.role == "sec_admin", "安全管理员把自己改成审计管理员，分权当场失效"


def test_cannot_delete_or_disable_self(client, admin_user, db_session):
    from app.models.user import User

    me = db_session.query(User).filter(User.username == "admin").one()
    h = _login(client, "admin", "AdminPass1")

    assert client.delete(f"/api/settings/users/{me.id}", headers=h).json()["code"] == 400
    assert client.put(
        f"/api/settings/users/{me.id}", json={"is_active": False}, headers=h
    ).json()["code"] == 400


def test_last_sys_admin_cannot_be_demoted(client, admin_user, sec_admin_user, db_session):
    """把最后一个在任系统管理员降权 = 没人能再建号 = 全平台锁死。

    这条护栏唯一够得着的路径就是**安全管理员改角色**。删/禁走不到这里：
    那两样需要 manage_accounts，而持钥匙的必然是另一个在任系统管理员，
    于是目标就不是「最后一个」了；剩下的自删自禁由「不能对自己动手」挡。
    """
    from app.models.user import User

    me = db_session.query(User).filter(User.username == "admin").one()
    hs = _login(client, "sec", "SecPass1!")

    resp = client.put(f"/api/settings/users/{me.id}/role", json={"role": "viewer"}, headers=hs)
    assert resp.json()["code"] == 400, "把最后一个系统管理员降权了"

    db_session.refresh(me)
    assert me.role == "sys_admin"


def test_second_sys_admin_frees_the_first(client, admin_user, sec_admin_user, db_session):
    """在任系统管理员不止一个时，降权/删除其中一个就放行了。"""
    from app.api.security import get_password_hash
    from app.models.user import User

    spare = User(
        username="admin2",
        password_hash=get_password_hash("Admin2Pass1"),
        nickname="A2",
        role="sys_admin",
        is_active=True,
    )
    db_session.add(spare)
    db_session.commit()
    db_session.refresh(spare)

    me = db_session.query(User).filter(User.username == "admin").one()
    hs = _login(client, "sec", "SecPass1!")
    resp = client.put(f"/api/settings/users/{me.id}/role", json={"role": "viewer"}, headers=hs)
    assert resp.json()["code"] == 200, resp.text

    # 现在只剩 admin2 在任 —— 再想降他，又该被挡
    resp = client.put(f"/api/settings/users/{spare.id}/role", json={"role": "viewer"}, headers=hs)
    assert resp.json()["code"] == 400

    # 换 admin2 用账号权删掉已降级的 admin —— 不是最后一个系统管理员，放行
    h2 = _login(client, "admin2", "Admin2Pass1")
    resp = client.delete(f"/api/settings/users/{me.id}", headers=h2)
    assert resp.json()["code"] == 200, resp.text


def test_permission_matrix_is_readable_by_anyone(client, viewer_user):
    """权限矩阵不是秘密 —— 它正是让人看懂「谁能干什么」的界面。"""
    h = _login(client, "viewer", "ViewPass1")
    resp = client.get("/api/settings/permissions", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["separation_of_powers"] == ["manage_accounts", "manage_authz", "audit"]
    assert [r["role"] for r in data["roles"]] == [
        "sys_admin", "sec_admin", "audit_admin", "operator", "viewer"
    ]
    assert data["my_role"] == "viewer"
    assert data["my_permissions"] == []


def test_me_reports_permissions(client, sec_admin_user):
    h = _login(client, "sec", "SecPass1!")
    data = client.get("/api/auth/me", headers=h).json()["data"]
    assert data["role"] == "sec_admin"
    assert set(data["permissions"]) == {"manage_authz", "operate"}
