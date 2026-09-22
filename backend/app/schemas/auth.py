"""
Authentication Schemas
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.utils.timezone import format_dt


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserInfo(BaseModel):
    id: int
    username: str
    nickname: str
    role: str


class LoginData(BaseModel):
    """Access token + refresh token. The SPA also receives both as HttpOnly cookies."""
    token: str
    refresh_token: str
    user: UserInfo


class LoginResponse(BaseModel):
    code: int = 200
    msg: str = "登录成功"
    data: LoginData


class RefreshResponse(BaseModel):
    code: int = 200
    msg: str = "刷新成功"
    data: LoginData


class UserResponse(BaseModel):
    id: int
    username: str
    nickname: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    login_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_serializer('last_login', 'created_at')
    def serialize_dt(self, dt: Optional[datetime], _info):
        return format_dt(dt)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    # Length/strength is enforced by app.core.policy.validate_password_strength
    # so the user gets one specific Chinese message instead of a bare 422.
    new_password: str = Field(..., min_length=1, max_length=128)
