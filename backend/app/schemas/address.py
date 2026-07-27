"""
Address Schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer

from app.utils.timezone import format_dt


class AddressCreate(BaseModel):
    """Create address request"""
    ip_address: str = Field(..., min_length=1, max_length=64)
    country: str = Field(default="", max_length=128)
    domain: str = Field(default="", max_length=256)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: int = Field(default=0, ge=0)
    attack_count: int = Field(default=0, ge=0)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    status: str = Field(default="active", pattern="^(active|blocked|whitelist)$")
    source: str = Field(default="", max_length=64)
    remark: str = Field(default="")


class AddressUpdate(BaseModel):
    """Update address request"""
    country: Optional[str] = None
    domain: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[int] = None
    attack_count: Optional[int] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    remark: Optional[str] = None


class AddressResponse(BaseModel):
    """Address response"""
    id: int
    ip_address: str
    country: str
    domain: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: int
    attack_count: int
    severity: str
    status: str
    source: str
    remark: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'start_time', 'end_time')
    def serialize_dt(self, dt: Optional[datetime], _info):
        return format_dt(dt)
