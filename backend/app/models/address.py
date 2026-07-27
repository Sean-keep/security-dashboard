"""
Address Model - Attack Address List
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base, TimestampMixin


class Address(Base, TimestampMixin):
    """Attack address model"""
    __tablename__ = "addresses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(64), nullable=False, index=True)
    country = Column(String(128), default="")
    domain = Column(String(256), default="")
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Integer, default=0)  # seconds
    attack_count = Column(Integer, default=0)
    severity = Column(String(32), default="medium")  # low/medium/high/critical
    status = Column(String(32), default="active")  # active/blocked/whitelist
    source = Column(String(64), default="")
    remark = Column(Text, default="")
    
    def __repr__(self):
        return f"<Address(id={self.id}, ip='{self.ip_address}', severity='{self.severity}')>"
