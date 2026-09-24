"""三权分立的结构性不变量。

路由级的 403 测的是「现在这个矩阵挡住了谁」；这里测的是「矩阵本身没被改坏」。
有人往 ROLE_PERMISSIONS 里给 sec_admin 加一行 manage_accounts，路由测试可能
一晚都跑不出来，但这几个断言会立刻炸。
"""
import pytest
from fastapi import HTTPException

from app.core.permissions import (
    PERMISSIONS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    SEPARATION_OF_POWERS,
    VALID_ROLES,
    assert_can_modify_account,
    has_permission,
    is_last_active_sys_admin,
    normalize_role,
    permission_matrix,
    permissions_for,
    validate_role_matrix,
)


def test_three_powers_each_held_by_exactly_one_role():
    for power in SEPARATION_OF_POWERS:
        holders = [r for r, ps in ROLE_PERMISSIONS.items() if power in ps]
        assert len(holders) == 1, f"「{power}」应独占于一个角色，实际在 {holders}"


def test_no_role_holds_two_of_the_three_powers():
    roles = list(ROLE_PERMISSIONS)
    for i, a in enumerate(roles):
        for b in roles[i + 1:]:
            both = [p for p in SEPARATION_OF_POWERS
                    if p in ROLE_PERMISSIONS[a] and p in ROLE_PERMISSIONS[b]]
            assert not both, f"「{a}」与「{b}」同时握有 {both} —— 三权分立被破坏"


def test_powers_are_on_the_right_roles():
    assert ROLE_PERMISSIONS["sys_admin"] & set(SEPARATION_OF_POWERS) == {"manage_accounts"}
    assert ROLE_PERMISSIONS["sec_admin"] & set(SEPARATION_OF_POWERS) == {"manage_authz"}
    assert ROLE_PERMISSIONS["audit_admin"] & set(SEPARATION_OF_POWERS) == {"audit"}


def test_every_role_has_a_label_and_description():
    for role in VALID_ROLES:
        assert ROLE_LABELS.get(role), role
        assert role in ROLE_PERMISSIONS


def test_matrix_covers_every_permission():
    rows = list(permission_matrix())
    assert len(rows) == len(VALID_ROLES)
    for row in rows:
        names = [p["name"] for p in row["permissions"]]
        assert names == list(PERMISSIONS)


# ── 勾选分配的校验规则（矩阵落库之后，这是最后一道闸） ─────────────
def _default_matrix():
    return {r: set(ps) for r, ps in ROLE_PERMISSIONS.items()}


def test_default_matrix_passes_validation():
    cleaned = validate_role_matrix(_default_matrix())
    assert cleaned["viewer"] == frozenset()


def test_validation_rejects_stacking_two_powers_on_one_role():
    """勾选分配也不能把账号+审计叠回一个角色 —— 那正是旧 admin 的毛病。"""
    m = _default_matrix()
    m["sys_admin"] = {"manage_accounts", "audit"}          # 叠
    m["audit_admin"] = set()                                # 审计被挪走了
    with pytest.raises(ValueError, match="三权互斥"):
        validate_role_matrix(m)


def test_validation_rejects_power_with_no_holder():
    m = _default_matrix()
    m["audit_admin"] = set()
    with pytest.raises(ValueError, match="无人持有"):
        validate_role_matrix(m)


def test_validation_rejects_power_with_two_holders():
    m = _default_matrix()
    m["operator"] = {"operate", "audit"}                    # 审计配了两把钥匙
    with pytest.raises(ValueError, match="只能落在一个角色上"):
        validate_role_matrix(m)


def test_validation_rejects_unknown_role_or_permission():
    m = _default_matrix()
    m["root"] = set()
    with pytest.raises(ValueError, match="未知角色"):
        validate_role_matrix(m)

    m = _default_matrix()
    m["operator"] = {"operate", "launch_missiles"}
    with pytest.raises(ValueError, match="未知权限点"):
        validate_role_matrix(m)


def test_validation_rejects_incomplete_matrix():
    m = _default_matrix()
    del m["viewer"]
    with pytest.raises(ValueError, match="缺少角色"):
        validate_role_matrix(m)


def test_free_permissions_are_not_restricted():
    """manage_system / operate 不是三权，勾给谁都行。"""
    m = _default_matrix()
    m["viewer"] = {"operate", "manage_system"}
    m["operator"] = set()
    cleaned = validate_role_matrix(m)
    assert cleaned["viewer"] == frozenset({"operate", "manage_system"})
    assert cleaned["operator"] == frozenset()


def test_legacy_admin_maps_to_sys_admin_and_never_to_viewer_as_admin():
    assert normalize_role("admin") == "sys_admin"
    # 不认识的角色降级成只读，绝不当管理员
    assert normalize_role("root") == "viewer"
    assert normalize_role("") == "viewer"
    assert normalize_role(None) == "viewer"


def test_viewer_holds_nothing():
    assert permissions_for("viewer") == frozenset()


def test_audit_admin_holds_only_audit():
    assert permissions_for("audit_admin") == frozenset({"audit"})


def test_has_permission_is_or_not_and():
    class _U:
        role = "sec_admin"

    assert has_permission(_U(), "manage_authz", "audit") is True   # 命中授权
    assert has_permission(_U(), "manage_accounts", "audit") is False  # 两个都没


# ── 账号管理护栏 ────────────────────────────────────────────────────
class _User:
    def __init__(self, id, role, is_active=True):
        self.id = id
        self.role = role
        self.is_active = is_active


def test_cannot_touch_yourself():
    me = _User(1, "sys_admin")
    for action in ("delete", "disable", "role-change"):
        with pytest.raises(HTTPException) as exc:
            assert_can_modify_account(me, me, action=action)
        assert exc.value.status_code == 400


def test_can_touch_someone_else():
    me = _User(1, "sys_admin")
    other = _User(2, "operator")
    assert_can_modify_account(me, other, action="delete")


def test_last_sys_admin_is_protected():
    last = _User(1, "sys_admin")
    assert is_last_active_sys_admin(last, 0) is True
    assert is_last_active_sys_admin(last, 1) is False
    # 不是系统管理员 / 已经禁用 —— 不受这条保护约束
    assert is_last_active_sys_admin(_User(2, "operator"), 0) is False
    assert is_last_active_sys_admin(_User(3, "sys_admin", is_active=False), 0) is False
    # 老角色名 admin 经 normalize_role 映射成 sys_admin，**同样**受保护 ——
    # 迁移没跑到的库里，最后一个老 admin 也不能被删掉。
    assert is_last_active_sys_admin(_User(4, "admin"), 0) is True
