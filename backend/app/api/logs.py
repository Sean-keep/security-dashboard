"""
Logs API Endpoints - 日志中心（登录日志 + 操作日志）
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.operation_log import OperationLog
from app.models.user import User
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user

router = APIRouter(prefix="/logs", tags=["Logs"])


class OperationLogResponse(BaseModel):
    """Operation log response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    log_type: Optional[str] = "operation"
    username: Optional[str] = ""
    action: Optional[str] = ""
    target: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[str] = "success"
    detail: Optional[str] = None
    created_at: Optional[datetime] = None


class OperationLogCreate(BaseModel):
    """Create operation log request"""
    log_type: str = "operation"  # login / operation
    username: str = ""
    action: str = ""
    target: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "success"  # success / failure
    detail: Optional[str] = None


def _parse_dt(val: str):
    """Parse a date/datetime string in common formats"""
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


@router.get("", response_model=PaginatedResponse[OperationLogResponse])
async def list_logs(
    log_type: str = Query(default="", description="Filter: ''=all, 'login', 'operation'"),
    keyword: str = Query(default="", description="Search username/action"),
    status: str = Query(default="", description="Filter by status success/failure"),
    date_from: str = Query(default="", description="Start date YYYY-MM-DD"),
    date_to: str = Query(default="", description="End date YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List logs with filtering and pagination"""
    from sqlalchemy import or_

    query = db.query(OperationLog)

    if log_type:
        query = query.filter(OperationLog.log_type == log_type)
    if keyword:
        query = query.filter(
            or_(
                OperationLog.username.like(f"%{keyword}%"),
                OperationLog.action.like(f"%{keyword}%"),
                OperationLog.target.like(f"%{keyword}%")
            )
        )
    if status:
        query = query.filter(OperationLog.status == status)

    if date_from:
        dt = _parse_dt(date_from)
        if dt:
            query = query.filter(OperationLog.created_at >= dt)
    if date_to:
        dt = _parse_dt(date_to)
        if dt:
            if len(date_to) <= 10:
                dt = dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OperationLog.created_at <= dt)

    query = query.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())

    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=[OperationLogResponse.model_validate(r) for r in rows]
        )
    )


@router.post("", response_model=Response[OperationLogResponse])
async def create_log(
    request: OperationLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Write an operation log entry"""
    log = OperationLog(
        log_type=request.log_type or "operation",
        username=request.username or current_user.username,
        action=request.action,
        target=request.target,
        ip_address=request.ip_address,
        status=request.status or "success",
        detail=request.detail
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return Response(msg="日志写入成功", data=OperationLogResponse.model_validate(log))
