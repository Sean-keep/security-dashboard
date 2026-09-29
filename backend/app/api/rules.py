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
from app.schemas.rule import RuleCreate, RuleUpdate, RuleResponse, MetricConfig
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user
from app.core.permissions import require_permission
from app.services.es_service import ESService, ESConfig
from app.services import rule_runner
from app.services.scheduler_service import SchedulerService
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


def _parse_metric_config(rule: Rule) -> Optional[Dict[str, Any]]:
    """读出 ``rules.metric_config``。坏 JSON 回 None，不抛。

    出站时**补齐 ``sustain_minutes``** —— 库里存的是 ``duration_seconds``（执行层
    的口径），表单填的是分钟（用户的口径）。少了这一项前端编辑弹窗会把「持续多久」
    显示成空的。
    """
    if not rule.metric_config:
        return None
    try:
        data = json.loads(rule.metric_config)
    except Exception:
        return None
    if not isinstance(data, dict) or not data:
        return None
    out = dict(data)
    duration = out.get("duration_seconds")
    if out.get("sustain_minutes") is None and duration is not None:
        try:
            out["sustain_minutes"] = max(1, int(int(duration) / 60))
        except (TypeError, ValueError):
            out["sustain_minutes"] = 5
    return out


def _metric_error(source_type: str, metric: Optional[MetricConfig],
                  has_stages: bool, has_nodes: bool) -> Optional[str]:
    """指标规则的形状校验。返回错误文案，合法返回 None。

    三条硬约束，都是被坑过才加的：
      * **stages 必须为空** —— 指标规则不查 ES，带着阶段配置只会让人以为它会查，
        然后在执行日志里看到 0 条结果却想不通。
      * **schedule 服务端强制**，不信客户端 —— 见 `create_rule` / `update_rule`。
      * **threshold 必须是有限数** —— pydantic 接受 NaN/Inf，而 NaN 参与比较
        永远是 False，规则会「保存成功但永远不触发」。
    """
    if source_type != "metric":
        return None
    if metric is None:
        return "指标规则必须填写 PromQL 与阈值配置"
    if not (metric.promql or "").strip():
        return "PromQL 表达式不能为空"
    if metric.operator not in (">", ">=", "<", "<=", "=="):
        return f"不支持的比较符「{metric.operator}」，可用：> >= < <= =="
    import math
    if not math.isfinite(metric.threshold):
        return "阈值必须是有限数字（不能是 NaN / 无穷大）"
    if metric.sustain_minutes < 1:
        return "持续时长必须至少 1 分钟"
    if has_stages:
        return "指标规则不支持查询阶段（它查的是 Grafana/Prometheus，不是 ES）"
    if has_nodes:
        return "指标规则不支持筛选节点"
    return None


def _force_metric_schedule(source_type: str) -> Dict[str, str]:
    """指标规则的服务端强制调度：固定每 60 秒检查。

    「持续 N 分钟」的语义建立在每分钟一次的观测上，让用户改间隔只会把计时搞乱
    ——填 30 分钟一次却说「持续 5 分钟」是自相矛盾的。表单上也不显示这一项。
    """
    if source_type == "metric":
        return {"schedule_type": "interval", "schedule_value": "60 seconds"}
    return {}


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
        "source_type": rule.source_type or "logs",
        "metric": _parse_metric_config(rule),
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



def _schedule_error(schedule_type: str, schedule_value: str) -> Optional[str]:
    """保存前校验调度参数。返回错误文案，合法则返回 None。

    早先这里什么都不校验 —— 存一条 `cron: 99 * * * *` 的规则会「保存成功」，
    然后永远不跑，界面上还看不出来（调度器那边只是 print 一行就 return）。
    """
    try:
        rule_runner.parse_schedule(schedule_type, schedule_value)
    except rule_runner.ScheduleError as exc:
        return str(exc)
    return None


@router.post("/schedule-preview", response_model=Response[Dict[str, Any]])
async def schedule_preview(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """调度参数预检：返回最近几次触发时间。

    和保存校验走同一条 `rule_runner.parse_schedule` —— 打字时说合法、存进去
    却不合法的两套逻辑以前是会分叉的。**故意不抛异常**，打到一半的表达式回
    `valid: false` 就行。
    """
    preview = rule_runner.preview_schedule(
        request.get("schedule_type", ""),
        request.get("schedule_value", ""),
        count=int(request.get("count", 3) or 3),
    )
    return Response(data=preview)


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
    current_user: User = Depends(require_permission("operate"))
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
    current_user: User = Depends(require_permission("operate"))
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


@router.post("/promql-test", response_model=Response[Dict[str, Any]])
async def promql_test(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operate"))
):
    """跑一次 PromQL，回显命中的 series 和当前值。不落库、不推进计时。

    和 `telegram-test` 同一个位置、同一个目的：让用户在保存规则之前就知道表达式
    写对没有 —— 否则只能等调度跑完才发现一直查不到数据。**只读**，绝不触碰
    `rule_metric_states`（点一下「测试」就把持续计时往前推是会误触发的）。
    """
    try:
        body = await request.json()
    except Exception:
        return Response(code=400, msg="请求体不是合法 JSON")

    promql = (body.get("promql") or "").strip()
    if not promql:
        return Response(code=400, msg="PromQL 表达式为空")

    from app.services import metrics_service

    resp = metrics_service.query_instant(db, promql)
    if not resp.ok:
        return Response(code=400, msg=f"查询失败：{resp.error or '未知错误'}", data={
            "total": 0, "series": [], "promql": promql,
        })

    rows = []
    for s in resp.series:
        if not metrics_service.is_usable(s.value):
            continue
        rows.append({
            "identity": s.labels.get("instance") or s.labels.get("node") or s.labels.get("pod") or "",
            "labels": s.labels,
            "value": s.value,
        })
    return Response(
        msg=f"查询成功，命中 {len(rows)} 条序列",
        data={"total": len(rows), "series": rows[:50], "promql": promql},
    )


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
    current_user: User = Depends(require_permission("operate"))
):
    """Create a new rule"""
    source_type = request.source_type or "logs"
    err = _metric_error(source_type, request.metric, bool(request.stages), bool(request.nodes))
    if err:
        return Response(code=400, msg=err)

    # 指标规则的调度由服务端强制（固定每 60 秒），不信客户端传上来的值。
    schedule_type = request.schedule_type
    schedule_value = request.schedule_value
    forced = _force_metric_schedule(source_type)
    if forced:
        schedule_type = forced["schedule_type"]
        schedule_value = forced["schedule_value"]

    err = _schedule_error(schedule_type, schedule_value)
    if err:
        return Response(code=400, msg=err)

    metric_json = "{}"
    if source_type == "metric" and request.metric is not None:
        metric_json = json.dumps({
            "promql": request.metric.promql.strip(),
            "operator": request.metric.operator,
            "threshold": request.metric.threshold,
            "duration_seconds": int(request.metric.sustain_minutes) * 60,
        }, ensure_ascii=False)

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
        source_type=source_type,
        metric_config=metric_json,
        schedule_type=schedule_type,
        schedule_value=schedule_value,
        is_enabled=request.is_enabled,
        actions=json.dumps(actions, ensure_ascii=False) if actions else "[]",
        created_by=current_user.id
    )
    
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # 调度器是独立进程（run_scheduler.py），这里够不着它的内存 JobStore。
    # 置脏位，run_scheduler 下一个 tick（≤5 秒）就会 reconcile。
    SchedulerService.mark_dirty()
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
    current_user: User = Depends(require_permission("operate"))
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
    if request.source_type is not None:
        update_data["source_type"] = request.source_type
    if request.metric is not None:
        update_data["metric_config"] = json.dumps({
            "promql": request.metric.promql.strip(),
            "operator": request.metric.operator,
            "threshold": request.metric.threshold,
            "duration_seconds": int(request.metric.sustain_minutes) * 60,
        }, ensure_ascii=False)

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
    
    # 校验「更新后的」形状，而不是只看本次提交了哪几个字段 ——
    # 只改 schedule_value 的 PUT 里 schedule_type 是 None，拿 None 去校验会误判。
    new_source = update_data.get("source_type", rule.source_type or "logs")
    new_metric: Optional[MetricConfig] = request.metric
    if new_metric is None:
        # 没提交 metric 就沿用库里那份，合成成 MetricConfig 去校验
        saved = _parse_metric_config(rule)
        if saved:
            try:
                new_metric = MetricConfig(
                    promql=saved.get("promql", ""),
                    operator=saved.get("operator", ">"),
                    threshold=float(saved.get("threshold", 0)),
                    sustain_minutes=max(1, int(int(saved.get("duration_seconds", 300)) / 60)),
                )
            except Exception:
                new_metric = None
    # stages / nodes 同理：只提交了一部分字段时，看的是**合并后**的规则会不会带 ES 阶段
    has_stages = bool(request.stages) if request.stages is not None else bool(json.loads(rule.stages or "[]"))
    has_nodes = bool(request.nodes) if request.nodes is not None else bool(json.loads(rule.nodes or "[]"))
    err = _metric_error(new_source, new_metric, has_stages, has_nodes)
    if err:
        return Response(code=400, msg=err)

    # 指标规则的调度由服务端强制
    forced = _force_metric_schedule(new_source)
    if forced:
        update_data["schedule_type"] = forced["schedule_type"]
        update_data["schedule_value"] = forced["schedule_value"]

    new_type = update_data.get("schedule_type", rule.schedule_type)
    new_value = update_data.get("schedule_value", rule.schedule_value)
    err = _schedule_error(new_type, new_value)
    if err:
        return Response(code=400, msg=err)

    # 条件变了 / 停用了 → 计时状态必须清掉。阈值从 80 改成 70 时，原来那条
    # 「已持续 4 分钟」的计时器会让新条件一上来就触发 —— 那是拿旧证据判新标准。
    old_metric_cfg = rule.metric_config or "{}"
    cfg_changed = (
        "metric_config" in update_data and update_data["metric_config"] != old_metric_cfg
    ) or ("source_type" in update_data and update_data["source_type"] != (rule.source_type or "logs"))
    disabled = update_data.get("is_enabled") is False

    for field, value in update_data.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)

    if (cfg_changed or disabled) and (rule.source_type or "") == "metric":
        from app.services import metric_rule_engine
        metric_rule_engine.clear_rule_states(db, rule.id)

    SchedulerService.mark_dirty()
    return Response(msg="规则更新成功", data=_rule_to_response(rule, db))


@router.delete("/{rule_id}", response_model=Response)
async def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operate"))
):
    """Delete rule"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")

    # 先清指标计时状态再删规则 —— rule_metric_states.rule_id 有外键，
    # MySQL InnoDB 下不先删子行会直接 1451。
    if (rule.source_type or "") == "metric":
        from app.services import metric_rule_engine
        metric_rule_engine.clear_rule_states(db, rule.id)

    db.delete(rule)
    db.commit()

    # 残留 job 由 SchedulerService.reconcile 清理
    SchedulerService.mark_dirty()
    return Response(msg="删除成功")


@router.post("/{rule_id}/run", response_model=Response)
async def run_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operate"))
):
    """Run rule (preview results, no write)"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")

    # 指标规则：只读快照。**绝不推进计时** —— 点一下「测试」就把「持续 N 分钟」
    # 往前推，会让人在正式跑之前莫名其妙提前触发。
    if (rule.source_type or "logs") == "metric":
        from app.services import metric_rule_engine
        snap = metric_rule_engine.preview_metric_rule(db, rule)
        if snap.get("no_data"):
            return Response(
                msg=f"无数据：{snap.get('error') or '查询未返回序列'}",
                data={"total": 0, "preview": [], "no_data": True},
            )
        return Response(
            msg=f"查询完成，共 {snap['total']} 条序列",
            data={"total": snap["total"], "preview": snap["preview"], "no_data": False},
        )

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
    current_user: User = Depends(require_permission("operate"))
):
    """执行规则（含 actions 写 MySQL）。

    业务逻辑在 `rule_runner.run_rule` —— 和调度器跑的是同一份，只有
    `triggered_by="manual"` 这个标记不同。早先这里是一份 90 行的重复拷贝，
    和 `scheduler_service` 里那个闭包各修各的，会走样。
    """
    result = rule_runner.run_rule(db, rule_id, triggered_by="manual", keep_preview=True)
    if result.error and result.error.startswith("规则 "):
        return Response(code=404, msg=result.error)
    if result.status != "success":
        return Response(code=500, msg=f"执行失败: {result.error or '未知错误'}")
    return Response(
        msg=f"执行完成，共 {result.total} 条记录，写入 {result.written} 条",
        data={
            "total": result.total,
            "written": result.written,
            "alert_count": result.alert_count,
            "duration_ms": result.duration_ms,
            "preview": result.preview,
        },
    )
