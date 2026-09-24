"""
三权分立权限模型

等保语境下的三权分立：**账号管理 / 授权 / 审计** 三项权力必须落在三个不同角色
上，任何用户都不能同时持有其中两项。于是没有任何一个人能「建个号、给上权、
再把痕迹抹掉」—— 建号的不能授权，授权的不能建号，看审计的两者都不能。

平台在此之上另留两级非特权角色，供日常写报告的人使用。干活不需要是管理员，
这也是三权能立得住的前提：如果每天写日报的人都得是管理员，分权只是摆设。

    权限点            sys_admin   sec_admin   audit_admin   operator   viewer
    ────────────────  ─────────   ─────────   ───────────   ────────   ──────
    manage_accounts   ✅           —            —             —          —
    manage_authz      —            ✅            —             —          —
    audit             —            —            ✅             —          —
    ────────────────  ─────────   ─────────   ───────────   ────────   ──────
    （以上三项即「三权」，每项只落在一个角色上）
    manage_system     ✅           —            —             —          —
    operate           ✅           ✅            —             ✅          —

    注：manage_accounts **不含改角色**。建号时的初始角色属「初始任命」，由系统
    管理员做；后续的角色变更属「授权」，只能由安全管理员做。两者分开是分权的
    关键一步。

矩阵**可以在线勾选分配**（PUT /settings/permissions），默认值就是上表，存在
``role_permissions`` 表里。能改矩阵的是系统管理员（manage_accounts）和安全
管理员（manage_authz）—— 岗位职责表由这两把钥匙的持有者共同维护。

但有三条底线是勾选也踩不得的，``validate_role_matrix`` 在保存路径上硬校验：

1. **三权互斥** —— 一个角色不能同时握两项三权。
2. **三权独占** —— 每项三权只落在一个角色上（一把钥匙不能配两把）。
3. **三权必须有人接** —— 每项三权至少一个角色持有，否则平台锁死。

``manage_system`` / ``operate`` 不受这三条约束，可以随意勾给任意角色。
"""
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.security import get_current_user
from app.models.base import get_db
from app.models.user import User


# ── 权限点 ──────────────────────────────────────────────────────────
PERMISSIONS: Tuple[str, ...] = (
    "manage_accounts",  # 用户增删、禁用、重置密码（不含改角色）
    "manage_authz",     # 修改用户角色（授权）
    "audit",            # 审计日志查看
    "manage_system",    # 系统配置、远程接口、脚本库、指标/别名配置
    "operate",          # 安全业务：规则 / 告警 / 地址 / 日报 / 脚本执行
)

# 三权分立的三项。校验用它，界面也用它。
SEPARATION_OF_POWERS: Tuple[str, ...] = ("manage_accounts", "manage_authz", "audit")

# 谁能勾选分配矩阵。建号的和授权的都能改岗位职责表 —— 但三权互斥让谁都没法
# 把三把钥匙叠到一个岗位上。用户说的「系统管理员勾选分配」走 manage_accounts 这把。
CAN_ASSIGN_MATRIX: Tuple[str, ...] = ("manage_accounts", "manage_authz")


# ── 角色 ────────────────────────────────────────────────────────────
VALID_ROLES: Tuple[str, ...] = (
    "sys_admin",
    "sec_admin",
    "audit_admin",
    "operator",
    "viewer",
)

ROLE_LABELS: Dict[str, str] = {
    "sys_admin": "系统管理员",
    "sec_admin": "安全管理员",
    "audit_admin": "审计管理员",
    "operator": "业务操作员",
    "viewer": "只读用户",
}

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "sys_admin": "账号增删禁用、系统配置、远程接口；可做日常安全业务。**不能改角色，不能看审计。**",
    "sec_admin": "角色授权（改用户角色）+ 安全策略与日常业务。**不能建号删号，不能看审计。**",
    "audit_admin": "只看审计（登录/操作日志）。**不能改系统，不能授权，不能改安全策略。**",
    "operator": "日常安全业务：写日报、处置告警、维护地址与规则。无任何管理权。",
    "viewer": "只读。可看仪表盘、列表、报告，不能写。",
}

# 内置默认矩阵。表里没这行（或表还没建）时的兜底，也是「恢复默认」的来源。
ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "sys_admin": frozenset({"manage_accounts", "manage_system", "operate"}),
    "sec_admin": frozenset({"manage_authz", "operate"}),
    "audit_admin": frozenset({"audit"}),
    "operator": frozenset({"operate"}),
    "viewer": frozenset(),
}

# 旧角色 → 新角色。迁移前的存量账号靠它继续工作；迁移脚本会把库里的值也改掉。
LEGACY_ROLE_MAP: Dict[str, str] = {
    "admin": "sys_admin",
}


def normalize_role(role: str) -> str:
    """把旧角色名映射到新模型；不认识的降级成只读，绝不当管理员。"""
    role = (role or "").strip()
    if role in ROLE_PERMISSIONS:
        return role
    return LEGACY_ROLE_MAP.get(role, "viewer")


# ── 矩阵的读写（落库，可在线勾选） ────────────────────────────────
def _encode(perms: Iterable[str]) -> str:
    """按 PERMISSIONS 的固定顺序编码，保证 diff 可读。"""
    return ",".join(p for p in PERMISSIONS if p in set(perms))


def _decode(raw: Optional[str]) -> FrozenSet[str]:
    return frozenset(p for p in (raw or "").split(",") if p)


def validate_role_matrix(matrix: Dict[str, Iterable[str]]) -> Dict[str, FrozenSet[str]]:
    """校验整张「角色 → 权限」矩阵。不合法抛 ``ValueError``。

    这是三权分立的最后一道闸：矩阵改成可勾选之后，唯一还能拦住「把三项权力
    叠回一个角色」的东西就是它。界面也按同样的规则做交互（三权列只能转移，
    不能空置、不能并存），但以这里为准。
    """
    if not matrix:
        raise ValueError("矩阵不能为空")

    unknown_roles = sorted(set(matrix) - set(VALID_ROLES))
    if unknown_roles:
        raise ValueError(f"未知角色：{unknown_roles}")

    missing_roles = sorted(set(VALID_ROLES) - set(matrix))
    if missing_roles:
        raise ValueError(f"矩阵缺少角色：{missing_roles}")

    cleaned: Dict[str, FrozenSet[str]] = {}
    for role, perms in matrix.items():
        perms = set(perms or [])
        unknown_perms = sorted(perms - set(PERMISSIONS))
        if unknown_perms:
            raise ValueError(f"角色「{ROLE_LABELS[role]}」含未知权限点：{unknown_perms}")
        cleaned[role] = frozenset(perms)

    # 1. 三权互斥 —— 一个角色不能同时握两项
    for role, perms in cleaned.items():
        held = [p for p in SEPARATION_OF_POWERS if p in perms]
        if len(held) > 1:
            raise ValueError(
                f"三权互斥：「{ROLE_LABELS[role]}」不能同时持有 {held}"
            )

    # 2 + 3. 每项三权有且仅有一个在任者
    for power in SEPARATION_OF_POWERS:
        holders = [r for r, ps in cleaned.items() if power in ps]
        if not holders:
            raise ValueError(
                f"三权「{power}」无人持有 —— 这块从此没人能管，平台会锁死"
            )
        if len(holders) > 1:
            labels = [ROLE_LABELS[r] for r in holders]
            raise ValueError(
                f"三权「{power}」只能落在一个角色上，当前在 {labels} 手上"
            )

    return cleaned


def load_role_permissions(db: Optional[Session] = None) -> Dict[str, FrozenSet[str]]:
    """读矩阵。表没建 / 缺行时回退到内置默认。

    不做进程内缓存：一次索引查询而已，容器是 ``--workers 1``，而测试是每个用例
    一个新库 —— 缓存反而会把上一个用例的勾选漏进下一个。
    """
    if db is None:
        return dict(ROLE_PERMISSIONS)

    from app.models.role_permission import RolePermission

    out = {role: set(perms) for role, perms in ROLE_PERMISSIONS.items()}
    try:
        rows = db.query(RolePermission).all()
    except Exception:
        # 表还没建（极早期启动）—— 用默认矩阵顶上，别把鉴权整条路打断
        return dict(ROLE_PERMISSIONS)

    for row in rows:
        if row.role in VALID_ROLES:
            out[row.role] = _decode(row.permissions)
    return {role: frozenset(perms) for role, perms in out.items()}


def ensure_role_permissions(db: Session) -> None:
    """把内置默认补进表里（只补缺失行，不覆盖已有勾选）。幂等。"""
    from app.models.role_permission import RolePermission

    existing = {r.role for r in db.query(RolePermission).all()}
    added = False
    for role, perms in ROLE_PERMISSIONS.items():
        if role in existing:
            continue
        db.add(RolePermission(role=role, permissions=_encode(perms), updated_by="seed"))
        added = True
    if added:
        db.commit()


def save_role_permissions(
    db: Session,
    matrix: Dict[str, Iterable[str]],
    updated_by: str = "",
) -> Dict[str, FrozenSet[str]]:
    """写整张矩阵。先过 ``validate_role_matrix``，不合法原样抛 ValueError。

    一次提交整张表而不是一次改一个角色 —— 三权独占是**跨角色**的约束，
    只改一行根本没法校验「这把钥匙是不是已经配给别人了」。
    """
    cleaned = validate_role_matrix(matrix)

    from app.models.role_permission import RolePermission

    rows = {r.role: r for r in db.query(RolePermission).all()}
    for role, perms in cleaned.items():
        raw = _encode(perms)
        if role in rows:
            rows[role].permissions = raw
            rows[role].updated_by = updated_by or ""
        else:
            db.add(RolePermission(role=role, permissions=raw, updated_by=updated_by or ""))
    db.commit()
    return cleaned


def permissions_for(role: str, db: Optional[Session] = None) -> FrozenSet[str]:
    role = normalize_role(role)
    return load_role_permissions(db).get(role, frozenset())


def has_permission(user: User, *perms: str, db: Optional[Session] = None) -> bool:
    """``perms`` 中任意一项命中即通过（OR）。"""
    if user is None:
        return False
    held = permissions_for(user.role, db)
    return any(p in held for p in perms)


def require_permission(*perms: str):
    """依赖工厂：用户必须持有 ``perms`` 中至少一项。

    参数是 OR 不是 AND —— 「系统管理员或安全管理员都能建号」这类写法靠 OR，
    而「既要 A 又要 B」在本模型里不存在（每个权限点就是一张通行证）。

    每次请求都读一次矩阵 —— 系统管理员勾了新权限，下一次请求立刻生效，不用
    重启。
    """
    if not perms:
        raise ValueError("require_permission 至少要一个权限点")

    async def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not has_permission(current_user, *perms, db=db):
            names = "/".join(perms)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires permission: {names}",
            )
        return current_user

    return _dep


# ── 启动自检：内置默认本身必须合法 ─────────────────────────────────
def _assert_separation_of_powers() -> None:
    """默认矩阵改坏时在 import 就炸，而不是等到有人登录才发现。

    在线勾选走的是 ``validate_role_matrix``（同一套规则，抛 ValueError 给接口
    回 400）。这里是常量层的自检，抛 RuntimeError 以示「代码写错了」。
    """
    try:
        validate_role_matrix({r: set(ps) for r, ps in ROLE_PERMISSIONS.items()})
    except ValueError as exc:
        raise RuntimeError(f"内置权限矩阵非法：{exc}") from exc

    unknown = set(ROLE_PERMISSIONS) - set(VALID_ROLES)
    if unknown:
        raise RuntimeError(f"ROLE_PERMISSIONS 里有未知角色：{unknown}")


_assert_separation_of_powers()


# ── 用户管理的互斥护栏（比路由鉴权更细） ───────────────────────────
def assert_can_modify_account(actor: User, target: User, *, action: str) -> None:
    """账号管理护栏。``action`` ∈ {'delete','disable','role-change'}。

    两条底线：
    1. 不能对自己动手（删掉/禁掉/把自己改成审计管理员去偷看日志）。
    2. 不能把最后一个在任系统管理员干掉 —— 否则没人能再建号，全平台锁死。
    """
    if actor.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "delete": "不能删除自己",
                "disable": "不能禁用自己",
                "role-change": "不能修改自己的角色",
            }.get(action, "不能对自己执行该操作"),
        )


def is_last_active_sys_admin(target: User, count_active_sys_admins) -> bool:
    """``count_active_sys_admins`` 是「除 target 外还有几个在任系统管理员」的计数。

    传入计数而不是 Session，是为了让这里不依赖 SQLAlchemy —— 单测可以直接
    喂数字，不用拉起数据库。
    """
    return (
        normalize_role(target.role) == "sys_admin"
        and bool(target.is_active)
        and count_active_sys_admins <= 0
    )


def permission_matrix(db: Optional[Session] = None) -> Iterable[dict]:
    """给前端「权限管理」页用的矩阵。顺序固定，和文档表格一致。"""
    matrix = load_role_permissions(db)
    for role in VALID_ROLES:
        yield {
            "role": role,
            "label": ROLE_LABELS[role],
            "description": ROLE_DESCRIPTIONS[role],
            "permissions": [
                {"name": p, "granted": p in matrix.get(role, frozenset())}
                for p in PERMISSIONS
            ],
        }
