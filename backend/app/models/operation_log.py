"""
Operation Log Model — 日志中心（登录日志 + 操作日志）
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base
from app.utils.timezone import local_now


class OperationLog(Base):
    """Unified operation/login log model"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_type = Column(String(50), default="operation", index=True)  # login / operation
    username = Column(String(100), default="")
    action = Column(String(255), default="")     # 操作描述
    target = Column(String(255), nullable=True)  # 操作对象
    ip_address = Column(String(50), nullable=True)
    status = Column(String(50), default="success")  # success / failure
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=local_now, index=True)

    def __repr__(self):
        return f"<OperationLog(id={self.id}, type='{self.log_type}', username='{self.username}', status='{self.status}')>"
