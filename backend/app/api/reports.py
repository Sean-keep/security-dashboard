"""
巡检报告 API
- GET  /api/reports/inspection?date=&script_ids=   生成报告（自动入库）
- GET  /api/reports              分页列表
- GET  /api/reports/{id}        预览（含 scripts stdout）
- DELETE /api/reports/{id}      删除
"""
import json
import time as _time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.user import User
from app.models.address import Address
from app.models.script import Script
from app.models.inspection_report import InspectionReport
from app.api.security import get_current_user
from app.api.inspect import _compute_server_metrics, _run_script
from app.utils.timezone import format_dt, now_cst
from app.schemas.common import Response

router = APIRouter(prefix="/api/reports", tags=["Reports"])


# ── Pydantic ──────────────────────────────────────────────────────────────────
class ReportGenResp(BaseModel):
    id: int
    report_date: str
    generated_at: str


# ── 生成报告（自动入库）───────────────────────────────────────────────────────
@router.get("/inspection", response_model=Response)
def inspection_report(
    date: str = Query(default="", description="报告日期 YYYY-MM-DD，默认今天（CST）"),
    script_ids: str = Query(default="", description="勾选执行的脚本ID，逗号分隔；为空则不执行任何脚本"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = now_cst()
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            day = now
    else:
        day = now
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)

    # Part 1: 地址列表
    addrs = (
        db.query(Address)
        .filter(Address.created_at >= day_start, Address.created_at <= day_end)
        .order_by(Address.attack_count.desc())
        .all()
    )
    addresses = [
        {
            "ip_address": a.ip_address,
            "country": a.country or "",
            "domain": a.domain or "",
            "start_time": format_dt(a.start_time),
            "end_time": format_dt(a.end_time),
            "duration": a.duration or 0,
            "attack_count": a.attack_count or 0,
        }
        for a in addrs
    ]

    # Part 2: 服务器监控（24 小时）
    is_today = day_start.date() == now.date()
    end_ts = int(_time.time()) if is_today else int(day_end.timestamp())
    servers, prom_url, err = _compute_server_metrics(db, end_ts, 86400)

    # Part 3: 脚本执行（仅勾选）
    scripts_out = []
    ids = []
    if script_ids:
        try:
            ids = [int(x) for x in script_ids.split(",") if x.strip()]
        except ValueError:
            ids = []
    if ids:
        rows = db.query(Script).filter(Script.id.in_(ids)).order_by(Script.id).all()
        for s in rows:
            try:
                r = _run_script(s.content, s.script_type, timeout=20)
                scripts_out.append({
                    "id": s.id,
                    "name": s.name,
                    "script_type": s.script_type,
                    "exit_code": r.get("exit_code"),
                    "stdout": (r.get("stdout") or "")[:3000],
                    "stderr": (r.get("stderr") or "")[:1000],
                })
            except Exception as e:
                scripts_out.append({
                    "id": s.id,
                    "name": s.name,
                    "script_type": s.script_type,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "执行异常: %s" % str(e),
                })

    generated_at_str = format_dt(now)
    report_date_str = day_start.strftime("%Y-%m-%d")

    # 组装 content（不含 stdout 详情，仅摘要）
    content = {
        "monitoring_window": "24 小时",
        "monitoring_connected": err is None,
        "monitoring_error": err,
        "addresses": addresses,
        "servers": servers,
        # scripts 预览仅含基本信息，不含 stdout
        "scripts_preview": [
            {
                "id": sc["id"],
                "name": sc["name"],
                "script_type": sc["script_type"],
                "exit_code": sc["exit_code"],
                "stderr": sc["stderr"][:200] if sc["stderr"] else "",
            }
            for sc in scripts_out
        ],
    }

    # 完整 scripts（含 stdout）存 scripts_json
    scripts_json_str = json.dumps(scripts_out, ensure_ascii=False)

    # 写入 DB
    rec = InspectionReport(
        report_date=report_date_str,
        generated_at=generated_at_str,
        address_count=len(addresses),
        script_count=len(scripts_out),
        content=json.dumps(content, ensure_ascii=False),
        scripts_json=scripts_json_str,
        created_by=current_user.username,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return Response(
        data={
            "id": rec.id,
            "report_date": report_date_str,
            "generated_at": generated_at_str,
            "address_count": len(addresses),
            "script_count": len(scripts_out),
            "addresses": addresses,
            "servers": servers,
            "monitoring_connected": err is None,
            "monitoring_error": err,
            "scripts": scripts_out,
        }
    )


# ── 报告列表 ──────────────────────────────────────────────────────────────────
@router.get("", response_model=Response)
def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    total = db.query(InspectionReport).count()
    rows = (
        db.query(InspectionReport)
        .order_by(InspectionReport.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        {
            "id": r.id,
            "report_date": r.report_date,
            "generated_at": r.generated_at,
            "address_count": r.address_count,
            "script_count": r.script_count,
            "created_by": r.created_by,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        }
        for r in rows
    ]
    return Response(data={"total": total, "items": items, "page": page, "page_size": page_size})


# ── 报告预览（含 stdout）───────────────────────────────────────────────────────
@router.get("/{report_id}", response_model=Response)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    r = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not r:
        return Response(code=404, msg="报告不存在")
    content = json.loads(r.content or "{}")
    scripts = json.loads(r.scripts_json or "[]")
    return Response(
        data={
            "id": r.id,
            "report_date": r.report_date,
            "generated_at": r.generated_at,
            "address_count": r.address_count,
            "script_count": r.script_count,
            "created_by": r.created_by,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "addresses": content.get("addresses", []),
            "servers": content.get("servers", []),
            "monitoring_connected": content.get("monitoring_connected"),
            "monitoring_error": content.get("monitoring_error"),
            "scripts_preview": content.get("scripts_preview", []),
            "scripts": scripts,
        }
    )


# ── 删除报告 ──────────────────────────────────────────────────────────────────
@router.delete("/{report_id}", response_model=Response)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    r = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not r:
        return Response(code=404, msg="报告不存在")
    db.delete(r)
    db.commit()
    return Response(msg="报告已删除")
