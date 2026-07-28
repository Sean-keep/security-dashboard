"""
Execution Log API Endpoints - 规则执行记录
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.user import User
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user

router = APIRouter(prefix="/execution-logs", tags=["ExecutionLogs"])


class ExecutionLogResponse(BaseModel):
    """Rule execution log response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    rule_name: Optional[str] = ""
    executed_at: Optional[str] = None
    alert_count: Optional[int] = 0
    detail: Optional[str] = ""
    status: Optional[str] = "success"
    error_message: Optional[str] = None

    @field_validator("executed_at", mode="before")
    @classmethod
    def format_datetime(cls, v):
        """Convert datetime to CST formatted string"""
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return v


@router.get("", response_model=PaginatedResponse[ExecutionLogResponse])
async def list_execution_logs(
    rule_id: Optional[int] = Query(default=None, description="Filter by rule id"),
    status: str = Query(default="", description="Filter by status success/error"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List rule execution logs with pagination"""
    where = []
    params = {}

    if rule_id is not None:
        where.append("rule_id = :rule_id")
        params["rule_id"] = rule_id
    if status:
        where.append("status = :status")
        params["status"] = status

    where_clause = " AND ".join(where) if where else "1=1"
    offset = (page - 1) * page_size

    # Count total
    total = db.execute(
        sa_text(f"SELECT COUNT(*) FROM rule_execution_logs WHERE {where_clause}"),
        params
    ).scalar() or 0

    # Query rows
    rows = db.execute(
        sa_text(f"""
            SELECT id, rule_id, rule_name, executed_at, alert_count,
                   detail, status, error_message
            FROM rule_execution_logs
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset}
    ).fetchall()

    items = []
    for r in rows:
        items.append(ExecutionLogResponse(
            id=r[0],
            rule_id=r[1],
            rule_name=r[2],
            executed_at=r[3],
            alert_count=r[4],
            detail=r[5],
            status=r[6],
            error_message=r[7]
        ))

    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=items
        )
    )


@router.get("/{log_id}", response_model=Response[ExecutionLogResponse])
async def get_execution_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get execution log detail"""
    row = db.execute(
        sa_text("""
            SELECT id, rule_id, rule_name, executed_at, alert_count,
                   detail, status, error_message
            FROM rule_execution_logs WHERE id = :id
        """),
        {"id": log_id}
    ).fetchone()

    if not row:
        return Response(code=404, msg="执行记录不存在")

    return Response(data=ExecutionLogResponse(
        id=row[0],
        rule_id=row[1],
        rule_name=row[2],
        executed_at=row[3],
        alert_count=row[4],
        detail=row[5],
        status=row[6],
        error_message=row[7]
    ))
