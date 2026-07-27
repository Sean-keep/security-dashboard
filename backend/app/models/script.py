"""
Script Model - Custom script storage
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from app.models.base import Base


class Script(Base):
    """Custom script model"""
    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, index=True)
    script_type = Column(String(32), default="python")  # python | shell
    description = Column(Text, default="")
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Script(id={self.id}, name='{self.name}', type='{self.script_type}')>"
