"""
Authentication Schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer

from app.utils.timezone import format_dt


class LoginRequest(BaseModel):
    """Login request"""
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserInfo(BaseModel):
    """User information in login response"""
    id: int
    username: str
    nickname: str
    role: str


class LoginData(BaseModel):
    """Login response data"""
    token: str
    user: UserInfo


class LoginResponse(BaseModel):
    """Login response"""
    code: int = 200
    msg: str = "登录成功"
    data: LoginData


class UserResponse(BaseModel):
    """User response"""
    id: int
    username: str
    nickname: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    login_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer('last_login', 'created_at')
    def serialize_dt(self, dt: Optional[datetime], _info):
        return format_dt(dt)


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)
