"""
Operation Log Model - 鏃ュ織涓績锛堢櫥褰曟棩蹇?+ 鎿嶄綔鏃ュ織锛?"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base


class OperationLog(Base):
    """Unified operation/login log model"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_type = Column(String(50), default="operation", index=True)  # login / operation
    username = Column(String(100), default="")
    action = Column(String(255), default="")  # 鎿嶄綔鎻忚堪
    target = Column(String(255), nullable=True)  # 鎿嶄綔瀵硅薄
    ip_address = Column(String(50), nullable=True)
    status = Column(String(50), default="success")  # success / failure
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    def __repr__(self):
        return f"<OperationLog(id={self.id}, type='{self.log_type}', username='{self.username}', status='{self.status}')>"
