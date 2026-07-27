"""
Alert Schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, field_serializer

from app.utils.timezone import format_dt


class AlertUpdate(BaseModel):
    """Update alert request"""
    status: Optional[str] = None
    severity: Optional[str] = None
    handle_suggestion: Optional[str] = None


class AlertResponse(BaseModel):
    """Alert response"""
    id: int
    rule_id: Optional[int] = None
    rule_name: str
    title: str
    content: str
    src_ip: str
    dst_ip: str
    event_count: int
    severity: str
    status: str
    category: str
    handle_suggestion: Optional[str] = None
    raw_log: str
    created_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'confirmed_at', 'resolved_at')
    def serialize_dt(self, dt: Optional[datetime], _info):
        return format_dt(dt)


class AlertStatsResponse(BaseModel):
    """Alert statistics response"""
    total: int
    today: int
    critical: int
    high: int
    pending: int
    trend: list
