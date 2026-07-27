"""
Authentication API Endpoints
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.user import User, LoginLog
from app.models.operation_log import OperationLog
from app.models.config import SystemConfig
from app.schemas.auth import LoginRequest, LoginResponse, LoginData, UserInfo, UserResponse, ChangePasswordRequest
from app.schemas.common import Response
from app.api.security import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_config(db: Session, key: str, default: str = "") -> str:
    """Get config value from database"""
    cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return cfg.value if cfg else default


def _check_ip_lockout(db: Session, ip: str) -> tuple[bool, str]:
    """
    Check if IP is locked out due to too many failed attempts.
    Returns (is_locked, lock_message)
    """
    max_attempts = int(_get_config(db, "login_max_attempts", "5"))
    lockout_minutes = int(_get_config(db, "login_lockout_minutes", "15"))
    
    recent_logs = db.query(LoginLog).filter(
        LoginLog.ip_address == ip,
        LoginLog.created_at > datetime.now() - timedelta(minutes=lockout_minutes)
    ).order_by(LoginLog.created_at.desc()).limit(max_attempts).all()
    
    if len(recent_logs) >= max_attempts:
        if recent_logs[0].status == "fail":
            return True, f"登录失败次数过多，账户已锁定 {lockout_minutes} 分钟"
    
    return False, ""


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)):
    """
    Login endpoint with security features:
    1. IP-based lockout after 5 failed attempts in 15 minutes
    2. Generic error message for wrong username/password
    """
    # Get client IP
    client_ip = req.headers.get("X-Forwarded-For", req.client.host) or "127.0.0.1"
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    
    # Check IP lockout
    locked, lock_msg = _check_ip_lockout(db, client_ip)
    if locked:
        db.add(LoginLog(username=request.username, ip_address=client_ip, status="locked", reason=lock_msg))
        db.add(OperationLog(
            log_type="login", username=request.username, action="登录",
            ip_address=client_ip, status="failure", detail=lock_msg
        ))
        db.commit()
        raise HTTPException(status_code=429, detail=lock_msg)
    
    # Find user
    user = db.query(User).filter(User.username == request.username).first()
    
    if not user:
        # Record failed login but return generic message
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
            user_agent=req.headers.get("User-Agent", "")
        ))
        db.add(OperationLog(
            log_type="login", username=request.username, action="登录",
            ip_address=client_ip, status="failure", detail="wrong_password"
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # Success: update user
    user.last_login = datetime.now()
    user.login_count = (user.login_count or 0) + 1
    user.error_count = 0
    
    db.add(LoginLog(username=request.username, ip_address=client_ip, status="success"))
    db.add(OperationLog(
        log_type="login", username=request.username, action="登录",
        ip_address=client_ip, status="success"
    ))
    
    # Create token
    token = create_access_token(data={"sub": str(user.id)})
    db.commit()
    
    return LoginResponse(
        code=200,
        msg="登录成功",
        data=LoginData(
            token=token,
            user=UserInfo(id=user.id, username=user.username, nickname=user.nickname, role=user.role)
        )
    )


@router.get("/me", response_model=Response[UserResponse])
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return Response(data=UserResponse(
        id=current_user.id,
        username=current_user.username,
        nickname=current_user.nickname,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login=current_user.last_login,
        login_count=current_user.login_count,
        created_at=current_user.created_at
    ))


@router.post("/change-password", response_model=Response)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password"""
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="原密码不正确")
    
    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()
    
    return Response(msg="密码修改成功")
