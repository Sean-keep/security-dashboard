"""
Settings API Endpoints - System Configuration
"""
from datetime import datetime

from app.utils.timezone import local_now
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.base import get_db
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.common import Response
from app.api.security import get_current_user, get_password_hash
from app.core.permissions import (
    CAN_ASSIGN_MATRIX,
    PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    SEPARATION_OF_POWERS,
    VALID_ROLES,
    assert_can_modify_account,
    ensure_role_permissions,
    has_permission,
    is_last_active_sys_admin,
    normalize_role,
    permission_matrix,
    permissions_for,
    require_permission,
    save_role_permissions,
)
from app.core.policy import validate_password_strength

router = APIRouter(prefix="/settings", tags=["Settings"])

# 出站一律不回传这类 key 的明文。TG 那套（_redact_actions + 留空保持）是同项目的
# 正确模板，这里补上 —— 早先 GET /settings/config 会把 es_password / mysql_password /
# grafana_api_key 等原样吐给任意登录用户，而 ConnectionPanel 界面上还显示成 ********。
_SECRET_KEY_MARKERS = ("password", "api_key", "apikey", "token", "secret")


def _is_runtime_key(key: str) -> bool:
    """运行态键 —— 调度器自己在写的东西，不是配置。

    早先 `scheduler_heartbeat` 会跟着 GET /settings/config 原样吐到系统设置页上，
    分组还是 `general`：一串 ISO 时间戳混在可编辑配置里，看着像坏了的字段，
    而且 PUT /settings/config 还允许人去改它 —— 改完调度器状态就假了。
    """
    k = (key or "").strip()
    return k.startswith("scheduler_") or k.startswith("runtime_")


def _is_secret_key(key: str) -> bool:
    k = (key or "").lower()
    return any(m in k for m in _SECRET_KEY_MARKERS)


def _mask_config_row(row: SystemConfig) -> dict:
    secret = _is_secret_key(row.key)
    return {
        "id": row.id,
        "key": row.key,
        # 密钥类只回传「是否已配置」，值永远是空串
        "value": "" if secret else row.value,
        "secret_set": bool((row.value or "").strip()) if secret else None,
        "label": row.label,
        "description": row.description,
        "group_name": row.group_name,
    }


# === User Management（三权分立） ===
#
# 账号管理（manage_accounts）和授权（manage_authz）是两把不同的钥匙：
#   系统管理员建号 / 禁用 / 重置密码 —— 建号时的初始角色属「初始任命」；
#   安全管理员改角色 —— 后续变更属「授权」。
# 把两件事塞进同一个接口（旧的 PUT /users 既改昵称又改角色）等于把两把钥匙
# 合成一把，三权分立从接口层就漏了。所以角色变更单独开一个路由。

class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str = ""
    role: str = "operator"
    is_active: bool = True


class UserUpdate(BaseModel):
    """账号资料。**故意不含 role** —— 改角色走 /users/{id}/role。"""
    nickname: str = None
    is_active: bool = None
    password: str = None


class UserRoleUpdate(BaseModel):
    role: str


def _user_row(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "role": u.role,
        "is_active": u.is_active,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "login_count": u.login_count or 0,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _count_other_active_sys_admins(db: Session, exclude_id: int) -> int:
    return (
        db.query(User)
        .filter(User.id != exclude_id, User.role == "sys_admin", User.is_active.is_(True))
        .count()
    )


@router.get("/users", response_model=Response[List[dict]])
async def list_users(
    db: Session = Depends(get_db),
    # 建号的人和授权的人都要能看到名单 —— 但只有各自那一半能动。
    current_user: User = Depends(require_permission("manage_accounts", "manage_authz")),
):
    """List all users. Held by 系统管理员（账号）and 安全管理员（授权）."""
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return Response(data=[_user_row(u) for u in rows])


@router.post("/users", response_model=Response)
async def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_accounts")),
):
    """Create a user (系统管理员). The role here is 初始任命 —— 后续变更归授权。"""
    try:
        validate_password_strength(request.password)
    except ValueError as exc:
        return Response(code=400, msg=str(exc))

    if db.query(User).filter(User.username == request.username).first():
        return Response(code=409, msg="用户名已存在")

    if request.role not in VALID_ROLES:
        return Response(code=400, msg=f"角色必须是 {'/'.join(VALID_ROLES)} 之一")

    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        nickname=request.nickname or request.username,
        role=request.role,
        is_active=request.is_active,
    )

    db.add(user)
    db.commit()

    return Response(msg="用户创建成功")


@router.put("/users/{user_id}", response_model=Response)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_accounts")),
):
    """Update account profile (系统管理员). 角色不在这里改 —— 见 /users/{id}/role。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return Response(code=404, msg="用户不存在")

    if request.nickname is not None:
        user.nickname = request.nickname

    if request.is_active is not None:
        if request.is_active is False:
            try:
                assert_can_modify_account(current_user, user, action="disable")
            except HTTPException as exc:
                return Response(code=400, msg=str(exc.detail))
            if is_last_active_sys_admin(user, _count_other_active_sys_admins(db, user.id)):
                return Response(code=400, msg="不能禁用最后一个在任系统管理员，否则没人能再建号")
        user.is_active = request.is_active

    if request.password:
        try:
            validate_password_strength(request.password)
        except ValueError as exc:
            return Response(code=400, msg=str(exc))
        user.password_hash = get_password_hash(request.password)

    db.commit()
    return Response(msg="更新成功")


@router.put("/users/{user_id}/role", response_model=Response)
async def update_user_role(
    user_id: int,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_authz")),
):
    """Change a user's role (安全管理员 only). 这就是「授权」那把钥匙。"""
    if request.role not in VALID_ROLES:
        return Response(code=400, msg=f"角色必须是 {'/'.join(VALID_ROLES)} 之一")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return Response(code=404, msg="用户不存在")

    try:
        assert_can_modify_account(current_user, user, action="role-change")
    except HTTPException as exc:
        return Response(code=400, msg=str(exc.detail))

    new_role = request.role
    # 降掉一个在任系统管理员之前，先确认还有别人能建号。
    if normalize_role(user.role) == "sys_admin" and new_role != "sys_admin":
        if is_last_active_sys_admin(user, _count_other_active_sys_admins(db, user.id)):
            return Response(code=400, msg="不能把最后一个在任系统管理员改成其他角色，否则没人能再建号")

    old_role = user.role
    user.role = new_role
    db.commit()
    return Response(
        msg=f"已将「{user.username}」的角色从 {ROLE_LABELS.get(normalize_role(old_role), old_role)} "
            f"改为 {ROLE_LABELS.get(new_role, new_role)}",
        data={"user_id": user.id, "old_role": old_role, "role": new_role},
    )


@router.delete("/users/{user_id}", response_model=Response)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_accounts")),
):
    """Delete user (系统管理员)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return Response(code=404, msg="用户不存在")

    try:
        assert_can_modify_account(current_user, user, action="delete")
    except HTTPException as exc:
        return Response(code=400, msg=str(exc.detail))

    if is_last_active_sys_admin(user, _count_other_active_sys_admins(db, user.id)):
        return Response(code=400, msg="不能删除最后一个在任系统管理员，否则没人能再建号")

    db.delete(user)
    db.commit()

    return Response(msg="删除成功")


@router.get("/permissions", response_model=Response[dict])
async def get_permission_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """三权分立矩阵 + 当前用户的权限点。任意登录用户可看 —— 这不是秘密，
    正是让人看懂「谁能干什么」的界面。矩阵存在 ``role_permissions`` 表里，
    系统管理员可在界面上勾选分配。"""
    ensure_role_permissions(db)
    return Response(data={
        "permissions": list(PERMISSIONS),
        "separation_of_powers": list(SEPARATION_OF_POWERS),
        "roles": list(permission_matrix(db)),
        "role_labels": ROLE_LABELS,
        "role_descriptions": ROLE_DESCRIPTIONS,
        # 「恢复默认」按钮的权威来源，不是前端那份副本
        "defaults": {r: sorted(ps) for r, ps in ROLE_PERMISSIONS.items()},
        "my_role": normalize_role(current_user.role),
        "my_permissions": sorted(permissions_for(current_user.role, db)),
        # 能不能进编辑态（勾选分配）。系统管理员走 manage_accounts 这把钥匙
        "can_assign": has_permission(current_user, *CAN_ASSIGN_MATRIX, db=db),
    })


class RolePermissionsUpdate(BaseModel):
    """整张「角色 → 权限」矩阵。**一次提交整张表** —— 三权独占是跨角色的约束，
    一次改一个角色没法校验「这把钥匙是不是已经配给别人了」。"""
    roles: Dict[str, List[str]]


@router.put("/permissions", response_model=Response)
async def save_permission_matrix(
    request: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(*CAN_ASSIGN_MATRIX)),
):
    """勾选分配角色权限矩阵（系统管理员 / 安全管理员）。

    三条底线由 ``validate_role_matrix`` 硬校验，勾也踩不过去：
    一个角色不能同时握两项三权；每项三权只认一个在任者；每项三权必须有人接。
    ``manage_system`` / ``operate`` 随意勾。
    """
    try:
        save_role_permissions(db, request.roles, updated_by=current_user.username)
    except ValueError as exc:
        return Response(code=400, msg=str(exc))
    return Response(
        msg="权限矩阵已更新",
        data={"roles": list(permission_matrix(db))},
    )


# === System Configuration ===

# 界面外观默认值。启动种子 + SQL 迁移都会建这些 key，这里再兜一层：SEED 关掉
# 且迁移没跑的库也能存外观配置 —— 界面管理页不该因为「key 不存在」而废掉。
# 只允许 ui_ 前缀的 key 走这条自动补建，其余未知 key 仍然照旧硬拒。
UI_CONFIG_DEFAULTS = {
    "ui_theme": ("light", "主题模式", "light 或 dark"),
    "ui_primary_color": ("#409eff", "主色", "Element Plus 主色（十六进制）"),
    "ui_density": ("default", "表格密度", "default / small / large"),
    "ui_sidebar_collapse": ("false", "侧边栏默认折叠", "true 或 false"),
    "ui_site_title": ("安全巡检平台", "站点标题", "侧边栏左上角显示的名称"),
}


def _ensure_ui_config(db: Session) -> dict:
    """补齐缺失的 ui_* 配置项，返回 key → SystemConfig 行。幂等。"""
    existing = {r.key: r for r in db.query(SystemConfig).filter(SystemConfig.key.like("ui_%")).all()}
    added = False
    for key, (val, label, desc) in UI_CONFIG_DEFAULTS.items():
        if key in existing:
            continue
        row = SystemConfig(key=key, value=val, label=label, description=desc, group_name="ui")
        db.add(row)
        existing[key] = row
        added = True
    if added:
        db.commit()
    return existing


@router.get("/config", response_model=Response[Dict[str, List[dict]]])
async def get_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all system config (grouped). Secret values are never returned.

    运行态键（scheduler_*）和 runtime 分组在这里被滤掉 —— 它们不是配置，
    见 ``_is_runtime_key``。
    """
    _ensure_ui_config(db)
    rows = db.query(SystemConfig).order_by(SystemConfig.group_name, SystemConfig.id).all()

    groups = {}
    for r in rows:
        if _is_runtime_key(r.key) or (r.group_name or "") == "runtime":
            continue
        groups.setdefault(r.group_name, []).append(_mask_config_row(r))

    return Response(data=groups)


class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, str]


@router.put("/config", response_model=Response)
async def save_config(
    request: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_system"))
):
    """Save system config (系统管理员).

    Secret keys are write-only: sending "" keeps the existing value (the form
    never has the real value back — see ``_mask_config_row``).
    Unknown keys are rejected loudly. They used to be dropped with ``continue``,
    so an admin could tighten ``login_max_attempts`` and get "保存成功" while
    ``saved=0`` and the runtime kept the env default — a silent policy failure.
    """
    _ensure_ui_config(db)
    rows = {r.key: r for r in db.query(SystemConfig).all()
            if not _is_runtime_key(r.key) and (r.group_name or "") != "runtime"}
    unknown = [k for k in request.updates if k not in rows]
    if unknown:
        return Response(
            code=400,
            msg=f"以下配置项不存在，未保存：{', '.join(sorted(unknown))}。"
                f"请先在系统配置初始化中加入这些 key。",
        )

    saved, kept = 0, []
    for key, value in request.updates.items():
        cfg = rows[key]
        text = str(value)
        if _is_secret_key(key) and not text.strip():
            # 留空 = 没改。绝不能把已配置的密钥冲成空串。
            kept.append(key)
            continue
        cfg.value = text
        cfg.updated_at = local_now()
        saved += 1

    db.commit()

    msg = f"配置保存成功，共更新 {saved} 项"
    if kept:
        msg += f"；{len(kept)} 项密钥留空已保持原值"
    return Response(msg=msg, data={"saved": saved, "kept": kept})


@router.get("/es-default", response_model=Response[dict])
async def get_es_default(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get ES default config for rule creation.

    The password is write-only: callers only learn whether one is configured.
    Rule creation never needs it — the backend reads ES creds from SystemConfig.
    """
    cfg_keys = ["es_host", "es_port", "es_scheme", "es_verify_certs", "es_user", "es_password", "es_index"]
    cfg = {}

    for key in cfg_keys:
        row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        cfg[key] = row.value if row else ""

    return Response(data={
        "host": cfg.get("es_host", "localhost"),
        "port": cfg.get("es_port", "9200"),
        "scheme": cfg.get("es_scheme", "https"),
        "verify_certs": cfg.get("es_verify_certs", "false"),
        "user": cfg.get("es_user", ""),
        # 不回传明文；建规则用不到它，后端自己从 SystemConfig 读
        "password": "",
        "password_set": bool((cfg.get("es_password") or "").strip()),
        "default_index": cfg.get("es_index", "security-logs-*")
    })


# === 连接测试（使用当前系统配置） ===

def _cfg(db, key, default=""):
    """从 SystemConfig 读取配置值"""
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row else default


def _build_es_client(db):
    """依据 SystemConfig 中的 ES 配置构造 Elasticsearch 客户端"""
    from elasticsearch import Elasticsearch

    host = _cfg(db, "es_host", "localhost") or "localhost"
    port = int(_cfg(db, "es_port", "9200") or "9200")
    scheme = _cfg(db, "es_scheme", "https") or "https"
    user = _cfg(db, "es_user", "")
    password = _cfg(db, "es_password", "")
    verify = (_cfg(db, "es_verify_certs", "false") or "false").lower() == "true"

    url = f"{scheme}://{host}:{port}"
    kwargs = {"verify_certs": verify, "request_timeout": 10}
    if user and password:
        kwargs["basic_auth"] = (user, password)
    return Elasticsearch([url], **kwargs)


@router.get("/test-es", response_model=Response[dict])
async def test_es(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """测试 ES 连接（使用当前配置的 ES 参数）"""
    import time
    try:
        start = time.time()
        client = _build_es_client(db)
        info = client.info()
        latency = round((time.time() - start) * 1000, 2)
        return Response(data={
            "connected": True,
            "latency_ms": latency,
            "cluster_name": info.get("cluster_name"),
            "version": info.get("version", {}).get("number") if isinstance(info.get("version"), dict) else None,
            "error": None
        })
    except Exception as e:
        return Response(code=400, msg="ES 连接失败", data={
            "connected": False,
            "error": str(e)[:300]
        })


@router.get("/test-mysql", response_model=Response[dict])
async def test_mysql(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """测试 MySQL 连接（使用当前配置的 MySQL 参数）"""
    import time
    import pymysql
    host = _cfg(db, "mysql_host", "localhost") or "localhost"
    port = int(_cfg(db, "mysql_port", "3306") or "3306")
    user = _cfg(db, "mysql_user", "root")
    password = _cfg(db, "mysql_password", "")
    database = _cfg(db, "mysql_database", "security_dashboard")
    try:
        start = time.time()
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=5, read_timeout=5
        )
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
        conn.close()
        latency = round((time.time() - start) * 1000, 2)
        return Response(data={
            "connected": True,
            "latency_ms": latency,
            "version": ver,
            "error": None
        })
    except Exception as e:
        return Response(code=400, msg="MySQL 连接失败", data={
            "connected": False,
            "error": str(e)[:300]
        })


@router.get("/test-prometheus", response_model=Response[dict])
async def test_prometheus(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """兼容旧接口，重定向到 Grafana"""
    return await test_grafana(db, current_user)


def _grafana_headers(db) -> dict:
    """根据配置构建 Grafana 请求头（支持 API Key 和 Basic Auth，含浏览器 UA）"""
    import base64
    auth_mode = _cfg(db, "grafana_auth_mode", "apikey")
    ua = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if auth_mode == "basic":
        user = _cfg(db, "grafana_user", "")
        pwd = _cfg(db, "grafana_password", "")
        if user and pwd:
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {**ua, "Authorization": f"Basic {token}"}
    else:
        api_key = _cfg(db, "grafana_api_key", "")
        if api_key:
            return {**ua, "Authorization": f"Bearer {api_key}"}
    return ua


@router.get("/test-grafana", response_model=Response[dict])
async def test_grafana(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """测试 Grafana 连接（支持 API Key 和 Basic Auth）
    区分：未配置 / 连接被拒绝 / 认证失败 / 成功
    """
    import urllib.request, ssl, urllib.error
    url = (_cfg(db, "grafana_url", "") or "").rstrip("/")
    if not url:
        return Response(code=400, msg="未配置 Grafana 地址，请在下方填入 Grafana URL，如 http://192.168.1.100:3000", data={
            "connected": False, "stage": "no_url", "error": "grafana_url 为空"
        })

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    auth_mode = _cfg(db, "grafana_auth_mode", "apikey")
    version_info = None
    stage = ""

    try:
        # 阶段1：带认证请求 /api/search
        # 必须带浏览器 UA，否则 CDN/代理会直接返回 403
        headers = _grafana_headers(db)
        test_url = url + "/api/search"
        req = urllib.request.Request(test_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            import json
            result = json.loads(resp.read().decode())
        stage = "auth_ok"

        # 阶段2：尝试 /api/health 获取版本
        try:
            health_url = url + "/api/health"
            req2 = urllib.request.Request(health_url, headers=_grafana_headers(db))
            with urllib.request.urlopen(req2, timeout=8, context=ctx) as r2:
                import json
                version_info = json.loads(r2.read().decode())
        except Exception:
            pass  # health 可选

        return Response(data={
            "connected": True,
            "stage": "ok",
            "version": version_info.get("version") if version_info else None,
            "commit": version_info.get("commit") if version_info else None,
            "auth_mode": auth_mode,
            "error": None
        })

    except urllib.error.HTTPError as e:
        if e.code == 401:
            # API Key 无效（401），自动尝试 Basic Auth 作为降级
            if auth_mode == "apikey":
                import base64
                basic_user = _cfg(db, "grafana_user", "")
                basic_pwd = _cfg(db, "grafana_password", "")
                if basic_user and basic_pwd:
                    try:
                        bt = base64.b64encode(f"{basic_user}:{basic_pwd}".encode()).decode()
                        fallback_req = urllib.request.Request(
                            url + "/api/search",
                            headers={
                                'Authorization': f'Basic {bt}',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            }
                        )
                        with urllib.request.urlopen(fallback_req, timeout=10, context=ctx) as fallback_resp:
                            import json
                            result = json.loads(fallback_resp.read().decode())
                        # Basic auth works! Key is invalid, switch suggestion
                        return Response(data={
                            "connected": True,
                            "stage": "ok_fallback_basic",
                            "auth_mode": "basic (API Key failed, auto-fallback)",
                            "basic_auth_works": True,
                            "note": "API Key 无效，已自动使用 Basic Auth 连接成功。建议重新生成 API Key 或改用 Basic Auth 认证模式。"
                        })
                    except Exception:
                        pass  # Basic auth also failed, fall through

                hint = (
                    "API Key 无效（HTTP 401）。"
                    "请重新生成 Grafana API Key（Grafana → Administration → API Keys → New API Key，角色选 Viewer）"
                )
                return Response(code=400, msg=hint, data={
                    "connected": False, "stage": "auth_invalid", "auth_mode": auth_mode,
                    "error": "HTTP 401: Unauthorized"
                })
            else:
                hint = "用户名或密码错误（HTTP 401），请确认 Grafana 账号密码正确。"
                return Response(code=400, msg=hint, data={
                    "connected": False, "stage": "auth_invalid", "auth_mode": auth_mode,
                    "error": "HTTP 401: Unauthorized"
                })
        elif e.code == 403:
            # 403 = credentials provided but access denied (possibly behind proxy/CF)
            if auth_mode == "apikey":
                hint = (
                    "API Key 验证被拒绝（HTTP 403）。"
                    "Grafana 可能部署在需要浏览器 Cookie 验证的代理/CDN 后面（如 Cloudflare），"
                    "此时 API Key 无法直接调用。"
                    "建议：1) 确认 Grafana 可直接 IP:Port 访问（不经过代理）；2) 或改用 Basic Auth 试试"
                )
            else:
                hint = "Basic Auth 被拒绝（HTTP 403），可能 Grafana 在代理/CDN 后面，账号密码无法直接认证。"
            return Response(code=400, msg=hint, data={
                "connected": False, "stage": "auth_forbidden", "auth_mode": auth_mode,
                "error": f"HTTP 403: Forbidden"
            })
        elif e.code == 404:
            return Response(code=400, msg="Grafana /api/search 返回 404，请确认 Grafana 版本（需 9.x+）", data={
                "connected": False, "stage": "not_found", "error": "HTTP 404"
            })
        else:
            return Response(code=400, msg=f"Grafana HTTP 错误: {e.code} {e.reason}", data={
                "connected": False, "stage": f"http_{e.code}", "error": f"HTTP {e.code}: {e.reason}"
            })
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "Connection refused" in reason:
            return Response(code=400, msg="Grafana 连接被拒绝，请确认 Grafana 已启动且地址/端口正确", data={
                "connected": False, "stage": "connection_refused",
                "grafana_url": url, "error": "Connection refused"
            })
        elif "timeout" in reason.lower():
            return Response(code=400, msg="Grafana 连接超时，请检查网络或防火墙设置", data={
                "connected": False, "stage": "timeout", "error": "连接超时"
            })
        elif "Name or service not known" in reason or "nodename nor servname" in reason:
            return Response(code=400, msg="Grafana 主机名无法解析，请检查 URL 是否正确", data={
                "connected": False, "stage": "dns_failed", "error": f"DNS 解析失败: {reason[:100]}"
            })
        else:
            return Response(code=400, msg=f"Grafana 连接失败: {reason[:200]}", data={
                "connected": False, "stage": "url_error", "error": reason[:200]
            })
    except Exception as e:
        return Response(code=400, msg=f"Grafana 连接异常: {str(e)[:200]}", data={
            "connected": False, "stage": "exception", "error": str(e)[:200]
        })


# === Login Logs ===

@router.get("/login-logs", response_model=Response[dict])
async def login_logs(
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    db: Session = Depends(get_db),
    # 审计日志独占 —— 系统管理员建号、安全管理员授权，但都看不到谁登录过。
    current_user: User = Depends(require_permission("audit"))
):
    """Get login logs（兼容接口，内部改为查询日志中心 OperationLog 表 log_type='login'）"""
    from app.models.operation_log import OperationLog

    query = db.query(OperationLog).filter(OperationLog.log_type == "login")
    if status:
        # 兼容旧参数：'fail'/'locked' → 'failure'
        mapped = "failure" if status in ("fail", "locked", "failure") else status
        query = query.filter(OperationLog.status == mapped)

    total = query.count()
    rows = query.order_by(OperationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    def _compat_status(s):
        # 兼容旧前端：'failure' → 'fail'
        return "fail" if s == "failure" else s

    return Response(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "list": [{
            "id": r.id,
            "username": r.username,
            "ip_address": r.ip_address,
            "status": _compat_status(r.status),
            "reason": r.detail or "",
            "created_at": r.created_at.isoformat() if r.created_at else None
        } for r in rows]
    })
