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
    status = Column(String(50), default="success")  # success / error / missed
    error_message = Column(Text, nullable=True)
    # 耗时（毫秒）和触发来源。有了这两个才能回答「这条规则怎么越来越慢」
    # 和「这次是谁跑的」—— 而不是把 trigger 埋进 detail 的 JSON 里查不了。
    # 列名不用 `trigger`：那是 MySQL 保留字。
    duration_ms = Column(Integer, default=0)
    triggered_by = Column(String(32), default="scheduler")  # scheduler / manual

    def __repr__(self):
        return f"<RuleExecutionLog(id={self.id}, rule_id={self.rule_id}, status='{self.status}')>"
