"""
Alerts API Endpoints - Security Alert Management
"""
import csv
import io
from datetime import datetime, timedelta
from typing import List

from app.utils.timezone import local_now, now_cst
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response as HTTPResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import case, func

from app.models.base import get_db
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, AlertUpdate
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user, require_roles

class BatchIdsRequest(BaseModel):
    """Batch IDs request body"""
    ids: List[int]

class BatchUpdateRequest(BaseModel):
    """Batch update request body"""
    ids: List[int]
    status: str


router = APIRouter(prefix="/alerts", tags=["Alerts"])

# 导出行数上限。与地址导出不同，告警的 raw_logs 可能是很大的 ES JSON，
# 不封顶的话一个宽时间窗就能拖垮内存和响应体。
EXPORT_MAX_ROWS = 20000


def _parse_dt(val):
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _apply_filters(query, keyword, status, severity, date_from, date_to):
    """列表与导出共用的筛选条件，保证「导出的就是当前筛出来的」。"""
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

    if date_from:
        dt = _parse_dt(date_from)
        if dt:
            query = query.filter(Alert.created_at >= dt)

    if date_to:
        _dt = _parse_dt(date_to)
        if _dt:
            # If date_to has no time component, treat as end-of-day
            if len(date_to) <= 10:
                _dt = datetime.strptime(date_to, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            query = query.filter(Alert.created_at <= _dt)

    return query


def _apply_sort(query, sort_field, sort_order):
    allowed_sort = {"created_at", "severity", "status", "event_count"}
    if sort_field not in allowed_sort:
        sort_field = "created_at"
    col = getattr(Alert, sort_field)
    return query.order_by(col.asc() if sort_order == "asc" else col.desc())


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
    query = _apply_filters(query, keyword, status, severity, date_from, date_to)
    query = _apply_sort(query, sort_field, sort_order)

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


def alert_counts_and_trend(db: Session) -> dict:
    """告警计数 + 7 天趋势。``GET /alerts/stats`` 与 ``GET /dashboard/stats`` 共用。

    Two GROUP BYs instead of twelve per-day COUNTs. The old loop also wrapped
    `created_at` in `func.date(...)`, which is non-sargable — it killed the
    index and scanned the whole table once per day bucket.
    """
    now = now_cst()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) 一张表扫一次拿到 total / today / critical / high / pending
    counts = dict(zip(
        ("total", "today", "critical", "high", "pending"),
        db.query(
            func.count(Alert.id),
            func.coalesce(func.sum(case((Alert.created_at >= today_start, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Alert.severity == "critical", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Alert.severity == "high", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Alert.status == "pending", 1), else_=0)), 0),
        ).one(),
    ))

    # 2) 7 天趋势：一次 GROUP BY，日期桶在 Python 侧补齐（区间小，且能吃上
    #    created_at 的索引）
    rows = (
        db.query(func.date(Alert.created_at), func.count(Alert.id))
        .filter(Alert.created_at >= week_start)
        .group_by(func.date(Alert.created_at))
        .all()
    )
    by_day = {str(d): n for d, n in rows}
    trend = []
    for i in range(7):
        day = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        trend.append({"date": day, "count": int(by_day.get(day, 0))})

    return {
        "total": int(counts["total"] or 0),
        "today": int(counts["today"] or 0),
        "critical": int(counts["critical"] or 0),
        "high": int(counts["high"] or 0),
        "pending": int(counts["pending"] or 0),
        "trend": trend,
    }


@router.get("/stats", response_model=Response[dict])
async def alert_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get alert statistics for dashboard."""
    return Response(data=alert_counts_and_trend(db))


@router.get("/export")
async def export_alerts(
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    severity: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出告警为 CSV（参数同列表查询，不分页）。

    路由必须写在 /{alert_id} 之前，否则 FastAPI 会把 "export" 当成 int 解析。
    不导出 raw_log / raw_logs：那是 ES 原始日志 JSON，体积会把 CSV 撑爆。
    """
    query = db.query(Alert)
    query = _apply_filters(query, keyword, status, severity, date_from, date_to)
    query = _apply_sort(query, sort_field, sort_order)
    rows = query.limit(EXPORT_MAX_ROWS).all()

    def _fmt_dt(v):
        return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""

    def _clean(v):
        # 自由文本换行会打断 CSV 行（虽然有引号包裹，Excel 仍经常显示错位）
        return (v or "").replace("\r\n", " ").replace("\n", " ")

    severity_cn = {"critical": "严重", "high": "高危", "medium": "中危", "low": "低危"}
    status_cn = {"pending": "待处理", "confirmed": "已确认", "resolved": "已解决", "false_positive": "误报"}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ID", "告警标题", "告警内容", "严重等级", "处理状态", "来源IP", "目的IP",
        "事件数", "分类", "触发规则", "处理建议", "产生时间", "确认时间", "解决时间",
    ])
    for a in rows:
        writer.writerow([
            a.id,
            _clean(a.title),
            _clean(a.content),
            severity_cn.get(a.severity, a.severity or ""),
            status_cn.get(a.status, a.status or ""),
            a.src_ip or "",
            a.dst_ip or "",
            a.event_count or 0,
            _clean(a.category),
            _clean(a.rule_name),
            _clean(a.handle_suggestion),
            _fmt_dt(a.created_at),
            _fmt_dt(a.confirmed_at),
            _fmt_dt(a.resolved_at),
        ])

    # 加 UTF-8 BOM，确保 Excel 正确识别中文
    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    filename = f"alerts_{local_now().strftime('%Y%m%d_%H%M%S')}.csv"

    return HTTPResponse(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


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
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Update alert status"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return Response(code=404, msg="告警不存在")
    
    if request.status:
        alert.status = request.status
        if request.status == "confirmed":
            alert.confirmed_at = local_now()
        elif request.status == "resolved":
            alert.resolved_at = local_now()
    
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
    current_user: User = Depends(require_roles("admin", "operator"))
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
    current_user: User = Depends(require_roles("admin", "operator"))
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
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Delete a single alert"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return Response(code=404, msg="告警不存在")

    db.delete(alert)
    db.commit()

    return Response(msg="删除成功")

