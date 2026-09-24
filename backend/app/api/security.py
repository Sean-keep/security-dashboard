"""
Security Utilities - JWT + Password Hashing

Tokens are delivered two ways:
1. ``Authorization: Bearer`` — for scripts / API clients (token is in the body
   of the login response).
2. ``HttpOnly; SameSite=Lax`` cookies — for the SPA, so an XSS cannot read the
   token out of ``localStorage``.

Access tokens are short-lived and carry ``type="access"``; refresh tokens carry
``type="refresh"`` and are only accepted by ``/api/auth/refresh``.
"""
from datetime import timedelta
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import get_db
from app.models.user import User
from app.utils.timezone import utc_now

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# auto_error=False so cookie-based clients (the SPA) can authenticate without
# an Authorization header.
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _encode(subject: str, token_type: str, expires_delta: timedelta) -> str:
    payload = {
        "sub": subject,
        "type": token_type,
        # jti makes every token byte-distinct. Without it two tokens minted in
        # the same second are identical, so a "rotation" is a silent no-op.
        "jti": uuid4().hex,
        "iat": utc_now(),
        "exp": utc_now() + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived access token. ``data`` must contain ``sub``."""
    subject = str(data.get("sub", ""))
    delta = expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = _encode(subject, "access", delta)
    # Preserve any extra claims callers pass (kept for compatibility).
    if len(data) > 1:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        for key, value in data.items():
            if key not in ("sub", "type", "exp", "iat"):
                payload[key] = value
        payload["exp"] = payload["exp"]
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token


def create_refresh_token(user_id: int) -> str:
    return _encode(
        str(user_id),
        "refresh",
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str = "access") -> Optional[int]:
    """Decode a JWT and return the user id, or None when invalid."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        # Reject refresh tokens used as access tokens (and vice versa).
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def decode_access_token(token: str) -> Optional[int]:
    return decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> Optional[int]:
    return decode_token(token, expected_type="refresh")


def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    request: Request,
) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(settings.ACCESS_COOKIE_NAME)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate via Bearer header or HttpOnly cookie."""
    token = _extract_token(credentials, request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return user


# 角色鉴权已迁到 app.core.permissions（三权分立）。
# 早先这里有 get_current_admin_user / require_roles，那是「admin 一把抓」的旧模型，
# 与三权分立直接冲突，所以删掉而不是留着当兼容层 —— 留着就有人绕过去用。
