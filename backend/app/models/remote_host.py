"""
Remote Host Model - 孤岛服务器标识（仅用于反向推送鉴权）
后端不主动连接目标，目标主动 POST 结果回来，用 token 鉴权。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.models.base import Base


class RemoteHost(Base):
    """远程孤岛主机（仅用于接收推送时鉴权与标识）"""
    __tablename__ = "remote_hosts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String(128), nullable=False, unique=True, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(64), default="")
