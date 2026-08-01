"""
Remote Execution Model - 孤岛服务器推送回来的脚本执行结果
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base


class RemoteExecution(Base):
    """远程脚本执行结果（孤岛主动推送）"""
    __tablename__ = "remote_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, nullable=False, index=True)
    host_alias = Column(String(128), default="")
    script_id = Column(Integer, nullable=True)
    script_name = Column(String(128), default="")
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    exit_code = Column(Integer, default=0)
    received_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
