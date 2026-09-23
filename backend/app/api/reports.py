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

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.user import User
from app.models.address import Address
from app.models.alert import Alert
from app.models.script import Script
from app.models.inspection_report import InspectionReport
from app.models.ingest_endpoint import IngestEndpoint
from app.models.ingest_log import IngestLog
from app.models.ingest_sender import IngestSender
from app.models.config import SystemConfig
from app.api.security import get_current_admin_user, get_current_user
from app.api.inspect import (
    _compute_server_metrics,
    _require_script_execution_enabled,
    _run_script,
)
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
    endpoint_ids: str = Query(default="", description="勾选整合的接收接口ID，逗号分隔；仅整合每个接口最近一条接收数据"),
    include_addresses: bool = Query(default=True, description="是否包含当日攻击地址"),
    include_monitoring: bool = Query(default=True, description="是否包含服务器监控"),
    summary_text: str = Query(default="", description="今日速览总结文本（手动填写）"),
    section_order: str = Query(default="", description="章节顺序快照（逗号分隔 key），导出时按此还原"),
    db: Session = Depends(get_db),
    # 会执行管理员录入的脚本 —— 与 /api/inspect/execute 同一道闸。
    # 早先这里是 get_current_user，等于给了任意登录用户一条绕过
    # get_current_admin_user 和 ENABLE_SCRIPT_EXECUTION 的执行通道。
    current_user: User = Depends(get_current_admin_user)
):
    _require_script_execution_enabled()
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
    if include_addresses:
        addrs = (
            db.query(Address)
            .filter(Address.created_at >= day_start, Address.created_at <= day_end)
            .order_by(Address.attack_count.desc())
            .all()
        )
        addresses = []
        for a in addrs:
            # 查询该 IP 最新告警的处置建议
            alert = (
                db.query(Alert)
                .filter(Alert.src_ip == a.ip_address, Alert.created_at >= day_start, Alert.created_at <= day_end)
                .order_by(Alert.created_at.desc())
                .first()
            )
            addresses.append({
                "ip_address": a.ip_address,
                "country": a.country or "",
                "domain": a.domain or "",
                "start_time": format_dt(a.start_time),
                "end_time": format_dt(a.end_time),
                "duration": a.duration or 0,
                "attack_count": a.attack_count or 0,
                "severity": a.severity or "medium",
                "handle_suggestion": alert.handle_suggestion if alert else "",
            })
    else:
        addresses = None

    # Part 2: 服务器监控（24 小时）
    if include_monitoring:
        is_today = day_start.date() == now.date()
        end_ts = int(_time.time()) if is_today else int(day_end.timestamp())
        servers, prom_url, err = _compute_server_metrics(db, end_ts, 86400)
    else:
        servers, err = None, None

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

    # Part 4: 接收端口（勾选的每个接口取最近一条）
    # 勾了就要 —— 不看 token，也不看绑定状态。绑定只用来认人/起名字，
    # 不是进日报的闸门；日报的闸门就是这个勾选。
    ingested = []
    if endpoint_ids:
        try:
            eids = [int(x) for x in endpoint_ids.split(",") if x.strip()]
        except ValueError:
            eids = []
        for eid in eids:
            ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == eid).first()
            if not ep:
                continue
            # 「最新一条」按源端发送时间排序，没有就退回接收顺序。
            # 早先固定 order_by(id.desc()) —— 重试送达的旧批次会顶掉新数据。
            log = (
                db.query(IngestLog)
                .filter(IngestLog.endpoint_id == eid)
                .order_by(IngestLog.sent_at.desc(), IngestLog.id.desc())
                .first()
            )
            sender_name = ""
            if log and log.sender_id:
                s = db.query(IngestSender).filter(IngestSender.id == log.sender_id).first()
                if s:
                    sender_name = s.display_name or s.src_ip or ""
            ingested.append({
                "endpoint_name": ep.name,
                "sender_name": sender_name,
                "received_at": log.received_at.strftime("%Y-%m-%d %H:%M:%S") if (log and log.received_at) else "",
                "payload": log.payload if log else "",
            })

    generated_at_str = format_dt(now)
    report_date_str = day_start.strftime("%Y-%m-%d")

    # 只存聚合值，不存 Prometheus 全量时序（每台约 864 点 × 3 条曲线）。
    # 预览只用 avg/peak，却把整段序列塞进 MEDIUMTEXT，报告一多就撑爆。
    servers_for_store = None
    if servers:
        servers_for_store = []
        for s in servers:
            slim = {k: v for k, v in s.items() if not k.endswith("_series")}
            if isinstance(slim.get("disks"), list):
                slim["disks"] = [
                    {k: v for k, v in d.items() if not k.endswith("_series")}
                    for d in slim["disks"]
                ]
            servers_for_store.append(slim)

    order_keys = [k.strip() for k in section_order.split(",") if k.strip()] or None

    # 组装 content（不含 stdout 详情，仅摘要）
    content = {
        "monitoring_window": "24 小时",
        "monitoring_connected": err is None,
        "monitoring_error": err,
        "addresses": addresses,
        "servers": servers_for_store,
        "ingested": ingested,
        "summary_text": summary_text,
        # 章节顺序随报告快照。导出必须读这里，不能读导出当下的 UI 状态，
        # 否则上周生成的报告会按今天点的顺序导出。
        "section_order": order_keys,
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

    # 同一天同一个人重复点「生成」是覆盖而不是插第二行 —— 双击不该出两份报告
    rec = (
        db.query(InspectionReport)
        .filter(
            InspectionReport.report_date == report_date_str,
            InspectionReport.created_by == current_user.username,
        )
        .first()
    )
    if rec is None:
        rec = InspectionReport(report_date=report_date_str, created_by=current_user.username)
        db.add(rec)
    rec.generated_at = generated_at_str
    rec.address_count = len(addresses) if addresses else 0
    rec.script_count = len(scripts_out)
    rec.content = json.dumps(content, ensure_ascii=False)
    rec.scripts_json = scripts_json_str
    db.commit()
    db.refresh(rec)

    return Response(
        data={
            "id": rec.id,
            "report_date": report_date_str,
            "generated_at": generated_at_str,
            "address_count": len(addresses) if addresses else 0,
            "script_count": len(scripts_out),
            "addresses": addresses,
            "servers": servers,
            "monitoring_connected": err is None,
            "monitoring_error": err,
            "scripts": scripts_out,
            "ingested": ingested,
            "summary_text": summary_text,
            "section_order": order_keys,
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


# ── 今日速览默认模板（可编辑保存，存 system_config）───────────────────
DEFAULT_SUMMARY_TEMPLATE = """1、无可用性问题，ospay线上服务器内存使用率峰值超过80%
2、nginx日志发现7个ip攻击行为，无入侵成功迹象
3、代理IP剩余流量:1116.17GB，预计还可使用111天（预计每天消耗10G）
4、短信网关余额:304.72372元，预计还可使用30天（预计每天消耗10）"""


def _get_report_template_cfg(db):
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "report_template").first()
    if cfg and cfg.value:
        try:
            return json.loads(cfg.value)
        except Exception:
            return {}
    return {}


@router.get("/summary-template", response_model=Response)
def get_summary_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """返回报告默认模板：template=今日速览文本，config=完整页面配置（勾选/顺序）"""
    cfg = _get_report_template_cfg(db)
    template = cfg.get("summary_text", "") or DEFAULT_SUMMARY_TEMPLATE
    return Response(data={"template": template, "config": cfg.get("config", {})})


@router.put("/summary-template", response_model=Response)
def save_summary_template(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    # 全局模板影响所有人生成的报告，收 admin
    current_user: User = Depends(get_current_admin_user)
):
    """保存报告默认模板。兼容两种入参：
    1. {template: "..."} — 仅保存今日速览文本（向后兼容）
    2. {template: "...", config: {...}} — 保存完整页面配置
    """
    template = str(body.get("template", "")).strip()
    if not template:
        return Response(code=400, msg="模板不能为空")
    config = body.get("config") or {}
    payload = {"summary_text": template, "config": config}
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "report_template").first()
    if cfg:
        cfg.value = json.dumps(payload, ensure_ascii=False)
    else:
        cfg = SystemConfig(
            key="report_template",
            value=json.dumps(payload, ensure_ascii=False),
            label="巡检报告默认模板",
            description="巡检报告完整页面配置（今日速览/勾选/顺序，可在页面上编辑保存）",
            group_name="report"
        )
        db.add(cfg)
    db.commit()
    return Response(msg="默认模板已保存")


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
            "ingested": content.get("ingested", []),
            "summary_text": content.get("summary_text", ""),
            "section_order": content.get("section_order"),
        }
    )


# ── 删除报告 ──────────────────────────────────────────────────────────────────
@router.delete("/{report_id}", response_model=Response)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    # 报告是审计产物，不能让任意登录用户销毁
    current_user: User = Depends(get_current_admin_user)
):
    r = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not r:
        return Response(code=404, msg="报告不存在")
    db.delete(r)
    db.commit()
    return Response(msg="报告已删除")
