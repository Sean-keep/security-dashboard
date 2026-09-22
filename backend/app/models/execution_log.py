"""
Rule Execution Log Model — 规则执行记录
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base
from app.utils.timezone import local_now


class RuleExecutionLog(Base):
    """Rule execution log model"""
    __tablename__ = "rule_execution_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False, index=True)
    rule_name = Column(String(255), default="")
    executed_at = Column(DateTime, default=local_now, index=True)
    alert_count = Column(Integer, default=0)       # 本次执行触发的告警数
    detail = Column(Text, default="")              # JSON 字符串：记录摘要信息
    status = Column(String(50), default="success")  # success / error
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RuleExecutionLog(id={self.id}, rule_id={self.rule_id}, status='{self.status}')>"
