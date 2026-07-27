"""
Alert Model - Security Alert
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.models.base import Base


class Alert(Base):
    """Security alert model"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=True)
    rule_name = Column(String(128), default="")
    
    title = Column(String(256), nullable=False)
    content = Column(Text, default="")
    
    # Associated IPs
    src_ip = Column(String(64), default="", index=True)
    dst_ip = Column(String(64), default="")
    event_count = Column(Integer, default=1)
    
    severity = Column(String(32), default="medium")  # low/medium/high/critical
    status = Column(String(32), default="pending")  # pending/confirmed/resolved/false_positive
    category = Column(String(64), default="")

    # 手动填写的处理建议
    handle_suggestion = Column(Text, default="")

    raw_log = Column(Text, default="")  # Raw log summary
    
    created_at = Column(DateTime, default=datetime.now, index=True)
    confirmed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Alert(id={self.id}, title='{self.title}', severity='{self.severity}')>"
