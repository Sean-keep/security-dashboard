"""
SystemConfig Model - Key-Value Configuration Storage
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base


class SystemConfig(Base):
    """System configuration KV model"""
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, default="")
    label = Column(String(128), default="")
    description = Column(String(256), default="")
    group_name = Column(String(64), default="general")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<SystemConfig(key='{self.key}', value='{self.value[:20]}...')>"
