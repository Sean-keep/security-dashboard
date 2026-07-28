"""
Rule Execution Log Model - 瑙勫垯鎵ц璁板綍
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base


class RuleExecutionLog(Base):
    """Rule execution log model"""
    __tablename__ = "rule_execution_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False, index=True)
    rule_name = Column(String(255), default="")
    executed_at = Column(DateTime, default=datetime.now, index=True)
    alert_count = Column(Integer, default=0)  # 瑙﹀彂鍛婅鏁?    detail = Column(Text, default="")  # JSON 瀛楃涓? 璁板綍鎽樿淇℃伅
    status = Column(String(50), default="success")  # success / error
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RuleExecutionLog(id={self.id}, rule_id={self.rule_id}, status='{self.status}')>"
