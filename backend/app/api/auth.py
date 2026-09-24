"""
Authentication API Endpoints
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.policy import validate_password_strength
from app.models.base import get_db
from app.models.user import User, LoginLog
from app.models.operation_log import OperationLog
from app.models.config import SystemConfig
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginData,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    UserInfo,
    UserResponse,
)
from app.schemas.common import Response
from app.api.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.utils.timezone import local_now

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_config(db: Session, key: str, default: str = "") -> str:
    cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return cfg.value if cfg else default


def get_client_ip(req: Request) -> str:
    """Resolve the client IP.

    Forwarded headers are only honoured when the deployment sets
    TRUSTED_PROXY_HEADERS=1, i.e. a proxy we control sets them. Otherwise they
    are trivially spoofable and would let an attacker dodge lockout.

    Two ordering rules that matter:

    * Prefer ``X-Real-IP``. nginx sets it with ``proxy_set_header X-Real-IP
      $remote_addr``, which **overwrites** any client-supplied value, so it is
      the TCP peer nginx saw.
    * If falling back to ``X-Forwarded-For``, take the **right-most** hop. Even
      ``$proxy_add_x_forwarded_for`` *appends* to the client-supplied header, so
      the left-most entry is attacker-controlled and can be used to rotate
      lockout keys. The right-most hop is the one our own proxy appended.

    Behind a proxy, without TRUSTED_PROXY_HEADERS=1, every request looks like
    it came from 127.0.0.1 and the lockout becomes global — turn the flag on
    whenever nginx (or similar) sits in front of uvicorn.
    """
    if settings.TRUSTED_PROXY_HEADERS:
        real_ip = (req.headers.get("X-Real-IP") or "").strip()
        if real_ip:
            return real_ip
        forwarded = (req.headers.get("X-Forwarded-For") or "").strip()
        if forwarded:
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if hops:
                return hops[-1]
    return (req.client.host if req.client else None) or "127.0.0.1"


def _check_ip_lockout(db: Session, ip: str) -> tuple[bool, str]:
    """Lock after N consecutive failures inside the window.

    A success resets the streak, so we count the trailing run of failures
    rather than "the newest row is a failure".
    """
    max_attempts = int(_get_config(db, "login_max_attempts", str(settings.LOGIN_MAX_ATTEMPTS)))
    lockout_minutes = int(_get_config(db, "login_lockout_minutes", str(settings.LOGIN_LOCKOUT_MINUTES)))

    recent_logs = (
        db.query(LoginLog)
        .filter(
            LoginLog.ip_address == ip,
            LoginLog.created_at > local_now() - timedelta(minutes=lockout_minutes),
        )
        .order_by(LoginLog.created_at.desc())
        .limit(max_attempts * 2)
        .all()
    )

    consecutive_failures = 0
    for log in recent_logs:
        if log.status in ("fail", "failure", "locked"):
            consecutive_failures += 1
            if consecutive_failures >= max_attempts:
                return True, f"登录失败次数过多，已锁定 {lockout_minutes} 分钟"
        else:
            # success resets the streak
            break

    return False, ""


def _set_auth_cookies(response: FastAPIResponse, access: str, refresh: str) -> None:
    secure = settings.COOKIE_SECURE
    common = {"httponly": True, "samesite": "lax", "secure": secure, "path": "/"}
    response.set_cookie(
        settings.ACCESS_COOKIE_NAME,
        access,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        **common,
    )


def _clear_auth_cookies(response: FastAPIResponse) -> None:
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    req: Request,
    response: FastAPIResponse,
    db: Session = Depends(get_db),
):
    """Login with IP-based lockout and a generic failure message."""
    client_ip = get_client_ip(req)

    locked, lock_msg = _check_ip_lockout(db, client_ip)
    if locked:
        db.add(LoginLog(username=request.username, ip_address=client_ip, status="locked", reason=lock_msg))
        db.add(OperationLog(
            log_type="login", username=request.username, action="登录",
            ip_address=client_ip, status="failure", detail=lock_msg
        ))
        db.commit()
        raise HTTPException(status_code=429, detail=lock_msg)

    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        db.add(LoginLog(username=request.username, ip_address=client_ip, status="fail", reason="user_not_found"))
        db.add(OperationLog(
            log_type="login", username=request.username, action="登录",
            ip_address=client_ip, status="failure", detail="user_not_found"
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用，请联系管理员")

    if not verify_password(request.password, user.password_hash):
        db.add(LoginLog(
            username=request.username,
            ip_address=client_ip,
            status="fail",
            reason="wrong_password",
            user_agent=req.headers.get("User-Agent", "")[:512],
        ))
        db.add(OperationLog(
            log_type="login", username=request.username, action="登录",
            ip_address=client_ip, status="failure", detail="wrong_password"
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login = local_now()
    user.login_count = (user.login_count or 0) + 1
    user.error_count = 0

    db.add(LoginLog(username=request.username, ip_address=client_ip, status="success"))
    db.add(OperationLog(
        log_type="login", username=request.username, action="登录",
        ip_address=client_ip, status="success"
    ))

    access = create_access_token(data={"sub": str(user.id)})
    refresh = create_refresh_token(user.id)
    db.commit()

    _set_auth_cookies(response, access, refresh)

    return LoginResponse(
        code=200,
        msg="登录成功",
        data=LoginData(
            token=access,
            refresh_token=refresh,
            user=UserInfo(id=user.id, username=user.username, nickname=user.nickname, role=user.role),
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: Request,
    response: FastAPIResponse,
    db: Session = Depends(get_db),
):
    """Exchange a refresh token for a fresh access token (and rotate refresh)."""
    token = (
        request.cookies.get(settings.REFRESH_COOKIE_NAME)
        or (request.headers.get("X-Refresh-Token") or "").strip()
    )
    if not token:
        raise HTTPException(status_code=401, detail="缺少刷新令牌")

    user_id = decode_refresh_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="账户不可用")

    access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(user.id)
    _set_auth_cookies(response, access, new_refresh)

    return RefreshResponse(code=200, msg="刷新成功", data=LoginData(
        token=access,
        refresh_token=new_refresh,
        user=UserInfo(id=user.id, username=user.username, nickname=user.nickname, role=user.role),
    ))


@router.post("/logout", response_model=Response)
async def logout(response: FastAPIResponse):
    """Clear auth cookies. Access tokens are stateless, so this is cookie-only."""
    _clear_auth_cookies(response)
    return Response(msg="已退出登录")


@router.get("/me", response_model=Response[UserResponse])
async def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 从库里读矩阵，不是从常量读 —— 系统管理员勾选分配之后 /me 要跟着变
    from app.core.permissions import permissions_for

    return Response(data=UserResponse(
        id=current_user.id,
        username=current_user.username,
        nickname=current_user.nickname,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login=current_user.last_login,
        login_count=current_user.login_count,
        created_at=current_user.created_at,
        permissions=sorted(permissions_for(current_user.role, db)),
    ))


@router.post("/change-password", response_model=Response)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="原密码不正确")

    try:
        validate_password_strength(request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if request.new_password == request.old_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")

    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()

    return Response(msg="密码修改成功")
