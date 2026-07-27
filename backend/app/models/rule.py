"""
Rule Model - Security Rule Configuration
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin


class Rule(Base, TimestampMixin):
    """Security rule model"""
    __tablename__ = "rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    
    # Legacy format: simple filter nodes (JSON)
    nodes = Column(Text, default="[]")
    
    # New format: multi-stage configuration (JSON)
    stages = Column(Text, default="[]")
    output_mapping = Column(Text, default="{}")
    
    # ES index
    es_index = Column(String(256), default="security-logs-*")
    
    # Schedule: once / interval / cron
    schedule_type = Column(String(32), default="once")
    schedule_value = Column(String(128), default="")  # interval seconds or cron expression
    is_enabled = Column(Boolean, default=True)
    
    # Actions when rule triggers (JSON)
    actions = Column(Text, default="[]")
    
    # Execution status
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    
    # Creator
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    def __repr__(self):
        return f"<Rule(id={self.id}, name='{self.name}', type='{self.schedule_type}')>"
