"""
首页概览聚合接口

前端 ``getDashboardStats`` 先打 ``GET /dashboard/stats``，404 才退回三个旧端点
拼装。这个路由就是那份契约：一次请求给齐地址数 / 规则数 / 告警统计 / 7 天趋势，
省掉三次往返，也省掉回退路径本身（回退还会因规则列表的 ``page_size`` 下限吃 422）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.alerts import alert_counts_and_trend
from app.api.security import get_current_user
from app.models.address import Address
from app.models.base import get_db
from app.models.rule import Rule
from app.models.user import User
from app.schemas.common import Response

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=Response)
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """首页概览卡片 + 趋势图所需的一切。只读，任意登录角色可看。"""
    alert = alert_counts_and_trend(db)
    return Response(data={
        "address_count": int(db.query(func.count(Address.id)).scalar() or 0),
        "rule_count": int(db.query(func.count(Rule.id)).scalar() or 0),
        "alert": alert,
        "trend": alert.get("trend") or [],
    })
