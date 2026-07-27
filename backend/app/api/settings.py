"""
Settings API Endpoints - System Configuration
"""
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.base import get_db
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.common import Response
from app.api.security import get_current_user, get_current_admin_user, get_password_hash

router = APIRouter(prefix="/settings", tags=["Settings"])


# === User Management ===

class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str = ""
    role: str = "operator"
    is_active: bool = True


class UserUpdate(BaseModel):
    nickname: str = None
    role: str = None
    is_active: bool = None
    password: str = None


@router.get("/users", response_model=Response[List[dict]])
async def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all users"""
    rows = db.query(User).order_by(User.created_at.desc()).all()
    
    return Response(data=[{
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "role": u.role,
        "is_active": u.is_active,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "login_count": u.login_count or 0,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in rows])


@router.post("/users", response_model=Response)
async def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new user (admin only)"""
    if len(request.password) < 6:
        return Response(code=400, msg="密码长度不能少于6位")
    
    if db.query(User).filter(User.username == request.username).first():
        return Response(code=409, msg="用户名已存在")
    
    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        nickname=request.nickname or request.username,
        role=request.role,
        is_active=request.is_active
    )
    
    db.add(user)
    db.commit()
    
    return Response(msg="用户创建成功")


@router.put("/users/{user_id}", response_model=Response)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return Response(code=404, msg="用户不存在")
    
    if request.nickname is not None:
        user.nickname = request.nickname
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password:
        if len(request.password) < 6:
            return Response(code=400, msg="密码长度不能少于6位")
        user.password_hash = get_password_hash(request.password)
    
    db.commit()
    return Response(msg="更新成功")


@router.delete("/users/{user_id}", response_model=Response)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete user (admin only)"""
    if user_id == current_user.id:
        return Response(code=400, msg="不能删除自己")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return Response(code=404, msg="用户不存在")
    
    db.delete(user)
    db.commit()
    
    return Response(msg="删除成功")


# === System Configuration ===

@router.get("/config", response_model=Response[Dict[str, List[dict]]])
async def get_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all system config (grouped)"""
    rows = db.query(SystemConfig).order_by(SystemConfig.group_name, SystemConfig.id).all()
    
    groups = {}
    for r in rows:
        if r.group_name not in groups:
            groups[r.group_name] = []
        groups[r.group_name].append({
            "id": r.id,
            "key": r.key,
            "value": r.value,
            "label": r.label,
            "description": r.description,
            "group_name": r.group_name
        })
    
    return Response(data=groups)


class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, str]


@router.put("/config", response_model=Response)
async def save_config(
    request: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Save system config (admin only)"""
    valid_keys = {r.key for r in db.query(SystemConfig).all()}

    saved = 0
    for key, value in request.updates.items():
        if key not in valid_keys:
            continue
        cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if cfg:
            cfg.value = str(value)
            cfg.updated_at = datetime.now()
            saved += 1
    
    db.commit()
    
    return Response(msg=f"配置保存成功，共更新 {saved} 项")


@router.get("/es-default", response_model=Response[dict])
async def get_es_default(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get ES default config for rule creation"""
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
        "password": cfg.get("es_password", ""),
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
    current_user: User = Depends(get_current_user)
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
