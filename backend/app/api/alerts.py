"""
Alerts API Endpoints - Security Alert Management
"""
from datetime import datetime, timedelta
from typing import List

from app.utils.timezone import now_cst
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.base import get_db
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, AlertUpdate
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user

class BatchIdsRequest(BaseModel):
    """Batch IDs request body"""
    ids: List[int]

class BatchUpdateRequest(BaseModel):
    """Batch update request body"""
    ids: List[int]
    status: str


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=PaginatedResponse[AlertResponse])
async def list_alerts(
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    severity: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List alerts with filtering"""
    query = db.query(Alert)
    
    if keyword:
        query = query.filter(
            (Alert.title.like(f"%{keyword}%")) |
            (Alert.content.like(f"%{keyword}%")) |
            (Alert.src_ip.like(f"%{keyword}%"))
        )
    
    if status:
        query = query.filter(Alert.status == status)
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    def _parse_dt(val):
        if not val:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        return None

    if date_from:
        dt = _parse_dt(date_from)
        if dt:
            query = query.filter(Alert.created_at >= dt)

    if date_to:
        _dt = _parse_dt(date_to)
        if _dt:
            # If date_to has no time component, treat as end-of-day
            if len(date_to) <= 10 or (len(date_to) == 19 and 'T' not in date_to and date_to[10] == ' '):
                if len(date_to) == 10:
                    _dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(Alert.created_at <= _dt)
    
    # Sorting
    allowed_sort = {"created_at", "severity", "status", "event_count"}
    if sort_field not in allowed_sort:
        sort_field = "created_at"
    
    col = getattr(Alert, sort_field)
    if sort_order == "asc":
        query = query.order_by(col.asc())
    else:
        query = query.order_by(col.desc())
    
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=[AlertResponse.model_validate(a) for a in rows]
        )
    )


@router.get("/stats", response_model=Response[dict])
async def alert_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get alert statistics for dashboard"""
    now = now_cst()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    total = db.query(Alert).count()
    today_count = db.query(Alert).filter(Alert.created_at >= today_start).count()
    critical = db.query(Alert).filter(Alert.severity == "critical").count()
    high = db.query(Alert).filter(Alert.severity == "high").count()
    pending = db.query(Alert).filter(Alert.status == "pending").count()
    
    # 7-day trend
    trend = []
    for i in range(7):
        day = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        cnt = db.query(Alert).filter(func.date(Alert.created_at) == day).count()
        trend.append({"date": day, "count": cnt})
    
    return Response(data={
        "total": total,
        "today": today_count,
        "critical": critical,
        "high": high,
        "pending": pending,
        "trend": trend
    })


@router.get("/{alert_id}", response_model=Response[AlertResponse])
async def get_alert(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get alert by ID"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return Response(code=404, msg="告警不存在")
    
    return Response(data=AlertResponse.model_validate(alert))


@router.put("/{alert_id}", response_model=Response[AlertResponse])
async def update_alert(
    alert_id: int,
    request: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update alert status"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return Response(code=404, msg="告警不存在")
    
    if request.status:
        alert.status = request.status
        if request.status == "confirmed":
            alert.confirmed_at = datetime.now()
        elif request.status == "resolved":
            alert.resolved_at = datetime.now()
    
    if request.severity:
        alert.severity = request.severity
    if request.handle_suggestion is not None:
        alert.handle_suggestion = request.handle_suggestion

    db.commit()
    db.refresh(alert)
    
    return Response(msg="更新成功", data=AlertResponse.model_validate(alert))


@router.post("/batch-update", response_model=Response)
async def batch_update(
    request: BatchUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Batch update alert status"""
    ids = request.ids
    status = request.status
    if not ids or not status:
        return Response(code=400, msg="参数不完整")
    
    db.query(Alert).filter(Alert.id.in_(ids)).update({"status": status}, synchronize_session=False)
    db.commit()
    
    return Response(msg=f"已更新 {len(ids)} 条告警")



@router.post("/batch-delete", response_model=Response)
async def batch_delete(
    request: BatchIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Batch delete alerts"""
    ids = request.ids
    if not ids:
        return Response(code=400, msg="参数不完整")

    count = db.query(Alert).filter(Alert.id.in_(ids)).delete(synchronize_session=False)
    db.commit()

    return Response(msg=f"已删除 {count} 条告警")


@router.delete("/{alert_id}", response_model=Response)
async def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a single alert"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return Response(code=404, msg="告警不存在")

    db.delete(alert)
    db.commit()

    return Response(msg="删除成功")

