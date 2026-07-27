"""
User and LoginLog Models
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.models.base import Base, TimestampMixin


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    nickname = Column(String(128), default="")
    role = Column(String(32), default="operator")  # admin / operator / viewer
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class LoginLog(Base):
    """Login log model"""
    __tablename__ = "login_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), index=True)
    ip_address = Column(String(64), index=True)
    user_agent = Column(String(512), default="")
    status = Column(String(32), default="fail")  # success / fail / locked
    reason = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.now, index=True)
    
    def __repr__(self):
        return f"<LoginLog(id={self.id}, username='{self.username}', status='{self.status}')>"
