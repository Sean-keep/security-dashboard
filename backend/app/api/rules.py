"""
Rules API Endpoints - Security Rule Management
"""
import orjson
from fastapi.responses import JSONResponse
import json
import copy
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.models.base import get_db
from app.models.rule import Rule
from app.models.alert import Alert
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user, require_roles
from app.services.es_service import ESService, ESConfig
from app.utils.timezone import format_dt, local_now

router = APIRouter(prefix="/rules", tags=["Rules"])


def _get_es_config(db: Session) -> ESConfig:
    """Get ES configuration from database"""
    cfg_keys = ["es_host", "es_port", "es_scheme", "es_verify_certs", "es_user", "es_password", "es_index"]
    cfg_values = {}
    
    for key in cfg_keys:
        cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        cfg_values[key] = cfg.value if cfg else ""
    
    return ESConfig(
        host=cfg_values.get("es_host", "localhost"),
        port=int(cfg_values.get("es_port", "9200")),
        scheme=cfg_values.get("es_scheme", "https"),
        verify_certs=cfg_values.get("es_verify_certs", "false").lower() == "true",
        user=cfg_values.get("es_user", ""),
        password=cfg_values.get("es_password", ""),
        default_index=cfg_values.get("es_index", "security-logs-*")
    )


def _get_es(db: Session) -> ESService:
    """Get ES service instance"""
    return ESService(config=_get_es_config(db))


def _inject_severity(actions: List[Dict], default_severity: str = "medium", severity_conditions: List = None) -> List[Dict]:
    """将危险等级和条件注入到 actions 中（写库前调用）"""
    if not actions:
        return []
    result = []
    for a in actions:
        a = dict(a)
        if "severity" not in a:
            a["severity"] = default_severity
        if severity_conditions:
            a["severity_conditions"] = [dict(c) if hasattr(c, "model_dump") else c for c in severity_conditions]
        result.append(a)
    return result


def _redact_actions(actions: List[Dict]) -> List[Dict]:
    """出站前抹掉 actions 里的密钥，只回传「是否已配置」。

    bot token 是密钥，不该跟着规则列表/详情回给每一个登录用户 —— 那等于
    把它放进了浏览器缓存和前端日志。前端用 bot_token_set 决定占位文案。
    """
    redacted = []
    for a in actions or []:
        a = dict(a)
        if a.get("type") == "telegram":
            token = a.pop("bot_token", "") or ""
            a["bot_token_set"] = bool(token.strip())
        redacted.append(a)
    return redacted


def _merge_telegram_secret(new_actions: List[Dict], old_actions: List[Dict]) -> List[Dict]:
    """更新时 bot_token 留空 = 保持原值。

    编辑弹窗拿不到明文 token（见 _redact_actions），所以「没改」和「清空」
    在载荷里长得一样，都必须解释成「保持原值」。要真正清掉只能填一个新值。
    """
    old_tokens = [a.get("bot_token", "") for a in (old_actions or []) if a.get("type") == "telegram"]
    merged = []
    idx = 0
    for a in new_actions or []:
        a = dict(a)
        if a.get("type") == "telegram":
            incoming = (a.get("bot_token") or "").strip()
            if not incoming:
                a["bot_token"] = old_tokens[idx] if idx < len(old_tokens) else ""
            a.pop("bot_token_set", None)
            idx += 1
        merged.append(a)
    return merged


def _alert_trend_for_rules(db: Session, rule_ids) -> Dict[int, Dict[str, int]]:
    """Daily alert counts for the last 7 days, for many rules in ONE query.

    Returns ``{rule_id: {"YYYY-MM-DD": count}}``. Days with no alerts are
    absent (callers treat a missing key as 0).
    """
    if not rule_ids:
        return {}
    today = local_now().date()
    window_start = datetime.combine(today - timedelta(days=6), datetime.min.time())
    day_col = func.date(Alert.created_at)
    rows = (
        db.query(Alert.rule_id, day_col, func.count(Alert.id))
        .filter(Alert.rule_id.in_(rule_ids), Alert.created_at >= window_start)
        .group_by(Alert.rule_id, day_col)
        .all()
    )
    out: Dict[int, Dict[str, int]] = {}
    for rule_id, day, count in rows:
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        out.setdefault(rule_id, {})[key] = int(count)
    return out


def _rule_to_response(rule: Rule, db: Session = None, counts_by_day: Dict[str, int] = None) -> Dict[str, Any]:
    """Convert Rule model to response dict.

    ``counts_by_day`` is the rule's pre-fetched trend (see
    ``_alert_trend_for_rules``) — pass it when serialising a list so the whole
    page costs one extra query instead of 7 per rule.
    """
    # Parse JSON fields
    stages = []
    if rule.stages:
        try:
            stages = json.loads(rule.stages)
        except Exception:
            pass

    nodes = []
    if rule.nodes:
        try:
            nodes = json.loads(rule.nodes)
            # Check if nodes contains stages format (backward compat)
            if nodes and isinstance(nodes, list) and isinstance(nodes[0], dict) and "index" in nodes[0]:
                stages = nodes
                nodes = []
        except Exception:
            pass

    output_mapping = {}
    if rule.output_mapping:
        try:
            output_mapping = json.loads(rule.output_mapping)
        except Exception:
            pass

    actions = []
    if rule.actions:
        try:
            actions = json.loads(rule.actions)
        except Exception:
            pass

    # 告警趋势（最近7天）。counts_by_day 可由调用方批量预取，避免 N+1。
    alert_trend = []
    alert_count = 0
    if db is not None or counts_by_day is not None:
        today = local_now().date()
        if counts_by_day is None:
            counts_by_day = _alert_trend_for_rules(db, [rule.id]).get(rule.id, {})
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            count = int(counts_by_day.get(day.isoformat(), 0))
            alert_trend.append({"date": day.strftime("%m-%d"), "count": count})
        alert_count = sum(item["count"] for item in alert_trend)

    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "es_index": rule.es_index,
        "schedule_type": rule.schedule_type,
        "schedule_value": rule.schedule_value,
        "is_enabled": rule.is_enabled,
        "last_run": format_dt(rule.last_run),
        "next_run": format_dt(rule.next_run),
        "alert_count": alert_count,
        "alert_trend": alert_trend,
        "created_at": format_dt(rule.created_at),
        "stages": stages,
        "output_mapping": output_mapping,
        "nodes": nodes,
        "actions": _redact_actions(actions)
    }


# ==================== Static Routes (MUST come before dynamic routes) ====================



@router.get("/scheduler/status", response_model=Response)
async def scheduler_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scheduler status"""
    try:
        from app.services.scheduler_service import SchedulerService
        ss = SchedulerService()
        jobs = []
        for job in ss.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(getattr(job, 'next_run_time', None) or ''),
                "trigger": str(job.trigger)
            })
        return Response(data={
            "running": ss.scheduler.running,
            "jobs": jobs
        })
    except Exception as e:
        return Response(code=500, msg=f"获取调度器状态失败: {str(e)}")
@router.get("/es-health", response_model=Response[Dict[str, Any]])
async def es_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get ES health status"""
    try:
        es = _get_es(db)
        health = es.check_health()
        return Response(data=health.model_dump())
    except Exception as e:
        return Response(code=500, msg=str(e))


@router.get("/es-indices", response_model=Response[List[Dict[str, Any]]])
async def es_indices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get ES index list"""
    try:
        es = _get_es(db)
        indices = es.list_indices()
        return Response(data=indices)
    except Exception as e:
        return Response(code=500, msg=str(e))


@router.post("/es-preview")
async def es_preview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """
    ES query preview (supports both old and new format)
    
    Old format: {"nodes": [...], "index": "...", "limit": 20}
    New format: {"stages": [...], "output_mapping": {...}, "limit": 20}
    """
    body = await request.json()
    limit = min(100, body.get("limit", 20))
    
    try:
        es = _get_es(db)
        
        stages = body.get("stages", [])
        output_mapping = body.get("output_mapping", {})
        
        if stages:
            results = es.execute_multi_stage_rule(stages, output_mapping, limit=limit)
            first_index = stages[0].get("index", "") if stages else ""
            fields = es.get_index_fields(first_index)
            body_resp = {"code": 200, "msg": "success", "data": {
                "total": len(results),
                "preview": results,
                "fields": fields,
                "stages": stages,
                "output_mapping": output_mapping
            }}
        else:
            nodes = body.get("nodes", [])
            index = body.get("index", es.config.default_index)
            results = es.execute_query(index, nodes, limit=limit)
            fields = es.get_index_fields(index)
            body_resp = {"code": 200, "msg": "success", "data": {
                "total": len(results),
                "preview": results,
                "fields": fields
            }}

        return JSONResponse(content=orjson.loads(orjson.dumps(body_resp)))

    except Exception as e:
        return JSONResponse(status_code=500, content=orjson.loads(orjson.dumps({"code": 500, "msg": str(e), "data": None})))


@router.post("/telegram-test", response_model=Response[Dict[str, Any]])
async def telegram_test(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """用当前表单里填的凭据发一条测试消息，不落库。

    让用户在保存规则之前就知道 token/chat_id 对不对 —— 否则只能等规则跑完
    才发现推送一直静默失败。
    """
    try:
        body = await request.json()
    except Exception:
        return Response(code=400, msg="请求体不是合法 JSON")

    bot_token = (body.get("bot_token") or "").strip()
    chat_id = (str(body.get("chat_id") or "")).strip()
    # 留空表示沿用已保存的凭据（前端编辑时拿不到明文 token，只拿到 bot_token_set）
    if not bot_token and body.get("rule_id"):
        saved = db.query(Rule).filter(Rule.id == body["rule_id"]).first()
        if saved and saved.actions:
            try:
                for a in json.loads(saved.actions):
                    if a.get("type") == "telegram" and (a.get("bot_token") or "").strip():
                        bot_token = a["bot_token"].strip()
                        break
            except Exception:
                pass

    from app.services.telegram_notify import send_telegram

    ok, err = send_telegram(
        bot_token,
        chat_id,
        "✅ 安全巡检平台 Telegram 推送测试成功",
    )
    if ok:
        return Response(msg="测试消息已发送，请查看 Telegram")
    return Response(code=400, msg=f"发送失败：{err}")


# ==================== CRUD Routes ====================


@router.get("", response_model=PaginatedResponse[Dict[str, Any]])
async def list_rules(
    keyword: str = Query(default=""),
    is_enabled: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List rules with filtering"""
    query = db.query(Rule)
    
    if keyword:
        query = query.filter(
            (Rule.name.like(f"%{keyword}%")) | (Rule.description.like(f"%{keyword}%"))
        )
    
    if is_enabled == "true":
        query = query.filter(Rule.is_enabled == True)
    elif is_enabled == "false":
        query = query.filter(Rule.is_enabled == False)
    
    total = query.count()
    rows = query.order_by(Rule.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # One grouped query for every rule's 7-day trend (was 7 queries per rule).
    trends = _alert_trend_for_rules(db, [r.id for r in rows])

    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=[_rule_to_response(r, db, counts_by_day=trends.get(r.id, {})) for r in rows]
        )
    )


@router.post("", response_model=Response[Dict[str, Any]])
async def create_rule(
    request: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Create a new rule"""
    # 注入危险等级到 actions。severity_conditions 是**每个 action 自己**的字段，
    # 不是 RuleCreate 顶层的 —— 早先那个 hasattr(...) 永远为 False，死代码。
    actions = _inject_severity(request.actions, request.severity)
    rule = Rule(
        name=request.name,
        description=request.description,
        nodes=json.dumps([n.model_dump() for n in request.nodes], ensure_ascii=False) if request.nodes else "[]",
        stages=json.dumps([s.model_dump() for s in request.stages], ensure_ascii=False) if request.stages else "[]",
        output_mapping=json.dumps({k: v.model_dump() for k, v in request.output_mapping.items()}, ensure_ascii=False) if request.output_mapping else "{}",
        es_index=request.es_index,
        schedule_type=request.schedule_type,
        schedule_value=request.schedule_value,
        is_enabled=request.is_enabled,
        actions=json.dumps(actions, ensure_ascii=False) if actions else "[]",
        created_by=current_user.id
    )
    
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # 调度器是独立进程（run_scheduler.py），这里够不着它的内存 JobStore。
    # 由 SchedulerService.reconcile 在下一个 tick 收敛，见 scheduler_service.py。
    return Response(msg="规则创建成功", data=_rule_to_response(rule, db))


@router.get("/{rule_id}", response_model=Response[Dict[str, Any]])
async def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get rule by ID"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    
    return Response(data=_rule_to_response(rule, db))


@router.put("/{rule_id}", response_model=Response[Dict[str, Any]])
async def update_rule(
    rule_id: int,
    request: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Update rule"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    
    # 直接从 request 对象获取原始数据，避免 Pydantic 转换问题
    update_data = {}

    # 只更新有值的字段
    if request.name is not None:
        update_data["name"] = request.name
    if request.description is not None:
        update_data["description"] = request.description
    if request.es_index is not None:
        update_data["es_index"] = request.es_index
    if request.schedule_type is not None:
        update_data["schedule_type"] = request.schedule_type
    if request.schedule_value is not None:
        update_data["schedule_value"] = request.schedule_value
    if request.is_enabled is not None:
        update_data["is_enabled"] = request.is_enabled

    # 处理 JSON 字段 - 直接序列化为字符串
    if request.stages is not None:
        stages_list = [s.model_dump() if hasattr(s, "model_dump") else s for s in request.stages]
        update_data["stages"] = json.dumps(stages_list, ensure_ascii=False)
    if request.nodes is not None:
        nodes_list = [n.model_dump() if hasattr(n, "model_dump") else n for n in request.nodes]
        update_data["nodes"] = json.dumps(nodes_list, ensure_ascii=False)
    if request.output_mapping is not None:
        mapping_dict = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in request.output_mapping.items()}
        update_data["output_mapping"] = json.dumps(mapping_dict, ensure_ascii=False)
    if request.actions is not None:
        # 注入危险等级
        actions_list = []
        for a in request.actions:
            if hasattr(a, "model_dump"):
                a_dict = a.model_dump()
            else:
                a_dict = dict(a)
            actions_list.append(a_dict)
        # bot_token 留空 = 保持原值（前端拿不到明文，只能这样表达「没改」）
        try:
            old_actions = json.loads(rule.actions) if rule.actions else []
        except Exception:
            old_actions = []
        actions_list = _merge_telegram_secret(actions_list, old_actions)
        update_data["actions"] = json.dumps(
            _inject_severity(actions_list, request.severity or "medium"),
            ensure_ascii=False
        )
    
    for field, value in update_data.items():
        setattr(rule, field, value)
    
    db.commit()
    db.refresh(rule)

    # 同上：调度参数的变更由 SchedulerService.reconcile 收敛
    return Response(msg="规则更新成功", data=_rule_to_response(rule, db))


@router.delete("/{rule_id}", response_model=Response)
async def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Delete rule"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")

    # 同上：残留 job 由 SchedulerService.reconcile 清理
    db.delete(rule)
    db.commit()

    return Response(msg="删除成功")


@router.post("/{rule_id}/run", response_model=Response)
async def run_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """Run rule (preview ES results, no write)"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    
    try:
        es = _get_es(db)
        
        # Check if multi-stage format
        stages = []
        output_mapping = {}
        
        if rule.stages:
            try:
                stages = json.loads(rule.stages)
                output_mapping = json.loads(rule.output_mapping) if rule.output_mapping else {}
            except Exception:
                pass
        
        if stages:
            results = es.execute_multi_stage_rule(stages, output_mapping)
        else:
            nodes = json.loads(rule.nodes or "[]")
            results = es.execute_query(rule.es_index, nodes)
        
        return Response(
            msg=f"查询完成，共 {len(results)} 条记录",
            data={"total": len(results), "preview": results[:20]}
        )
    
    except Exception as e:
        return Response(code=500, msg=f"ES查询失败: {str(e)}")

@router.post("/{rule_id}/execute", response_model=Response)
async def execute_rule_endpoint(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator"))
):
    """执行规则（含 actions 写 MySQL）"""
    from datetime import datetime
    from app.services.rule_executor import RuleExecutor

    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    try:
        es = _get_es(db)
        stages = []
        output_mapping = {}
        if rule.stages:
            try:
                stages = json.loads(rule.stages)
                output_mapping = json.loads(rule.output_mapping) if rule.output_mapping else {}
            except Exception:
                pass
        if stages:
            results = es.execute_multi_stage_rule(stages, output_mapping)
        else:
            nodes = json.loads(rule.nodes or "[]")
            results = es.execute_query(rule.es_index, nodes)
        from app.services.rule_executor import reverse_output_mapping
        results = reverse_output_mapping(output_mapping, results)

        actions = json.loads(rule.actions or "[]")
        # 给每个动作带上规则元数据。create_alert 和 telegram 都要规则名，
        # write_mysql 忽略这几个键也没副作用。
        for act in actions:
            act["_rule_id"] = rule.id
            act["_rule_name"] = rule.name
            act["_rule_severity"] = getattr(rule, "severity", "medium")
        executor = RuleExecutor(db)
        written = executor.process_actions(actions, results)

        # 存储触发告警的ES原始日志
        if executor.created_alert_ids and stages:
            from app.services.scheduler_service import _store_raw_logs_for_alerts
            _store_raw_logs_for_alerts(db, es, stages, executor.created_alert_ids)

        rule.last_run = local_now()
        rule.run_count = (rule.run_count or 0) + 1
        db.commit()

        # 记录执行日志
        from app.services.rule_executor import record_execution_log
        record_execution_log(
            db,
            rule_id=rule.id,
            rule_name=rule.name,
            alert_count=executor.last_alert_count,
            detail={
                "trigger": "manual",
                "total_results": len(results),
                "mysql_written": executor.last_mysql_written,
                "alert_created": executor.last_alert_count,
                "total_written": written
            },
            status="success"
        )

        return Response(
            msg=f"执行完成，共 {len(results)} 条记录，写入 {written} 条",
            data={"total": len(results), "written": written, "preview": results[:20]}
        )
    except Exception as e:
        db.rollback()
        try:
            from app.services.rule_executor import record_execution_log
            record_execution_log(
                db,
                rule_id=rule.id,
                rule_name=rule.name,
                alert_count=0,
                detail={"trigger": "manual"},
                status="error",
                error_message=str(e)[:2000]
            )
        except Exception:
            pass
        return Response(code=500, msg=f"执行失败: {str(e)}")
