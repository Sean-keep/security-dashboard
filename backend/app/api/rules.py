"""
Rules API Endpoints - Security Rule Management
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.base import get_db
from app.models.rule import Rule
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user
from app.services.es_service import ESService, ESConfig
from app.utils.timezone import format_dt

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


def _rule_to_response(rule: Rule) -> Dict[str, Any]:
    """Convert Rule model to response dict"""
    # Parse JSON fields
    stages = []
    if rule.stages:
        try:
            stages = json.loads(rule.stages)
        except:
            pass
    
    nodes = []
    if rule.nodes:
        try:
            nodes = json.loads(rule.nodes)
            # Check if nodes contains stages format (backward compat)
            if nodes and isinstance(nodes, list) and isinstance(nodes[0], dict) and "index" in nodes[0]:
                stages = nodes
                nodes = []
        except:
            pass
    
    output_mapping = {}
    if rule.output_mapping:
        try:
            output_mapping = json.loads(rule.output_mapping)
        except:
            pass
    
    actions = []
    if rule.actions:
        try:
            actions = json.loads(rule.actions)
        except:
            pass
    
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
        "run_count": rule.run_count,
        "created_at": format_dt(rule.created_at),
        "stages": stages,
        "output_mapping": output_mapping,
        "nodes": nodes,
        "actions": actions
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


@router.post("/es-preview", response_model=Response)
async def es_preview(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ES query preview (supports both old and new format)
    
    Old format: {"nodes": [...], "index": "...", "limit": 20}
    New format: {"stages": [...], "output_mapping": {...}, "limit": 20}
    """
    limit = min(100, request.get("limit", 20))
    
    try:
        es = _get_es(db)
        
        stages = request.get("stages", [])
        output_mapping = request.get("output_mapping", {})
        
        if stages:
            results = es.execute_multi_stage_rule(stages, output_mapping, limit=limit)
            first_index = stages[0].get("index", "") if stages else ""
            fields = es.get_index_fields(first_index)
            return Response(data={
                "total": len(results),
                "preview": results,
                "fields": fields,
                "stages": stages,
                "output_mapping": output_mapping
            })
        else:
            nodes = request.get("nodes", [])
            index = request.get("index", es.config.default_index)
            results = es.execute_query(index, nodes, limit=limit)
            fields = es.get_index_fields(index)
            return Response(data={
                "total": len(results),
                "preview": results,
                "fields": fields
            })
    
    except Exception as e:
        return Response(code=500, msg=str(e))


# ==================== CRUD Routes ====================


@router.get("", response_model=PaginatedResponse[Dict[str, Any]])
async def list_rules(
    keyword: str = Query(default=""),
    is_enabled: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=10, le=200),
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
    
    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=[_rule_to_response(r) for r in rows]
        )
    )


@router.post("", response_model=Response[Dict[str, Any]])
async def create_rule(
    request: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new rule"""
    # 注入危险等级到 actions
    actions = _inject_severity(request.actions, request.severity, request.severity_conditions if hasattr(request, "severity_conditions") else [])
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
    
    # TODO: Add to scheduler if interval/cron
    
    return Response(msg="规则创建成功", data=_rule_to_response(rule))


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
    
    return Response(data=_rule_to_response(rule))


@router.put("/{rule_id}", response_model=Response[Dict[str, Any]])
async def update_rule(
    rule_id: int,
    request: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update rule"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    
    update_data = request.model_dump(exclude_unset=True)
    
    # Handle JSON fields
    if "stages" in update_data and update_data["stages"]:
        update_data["stages"] = json.dumps([s.model_dump() if hasattr(s, "model_dump") else s for s in update_data["stages"]], ensure_ascii=False)
    if "nodes" in update_data and update_data["nodes"]:
        update_data["nodes"] = json.dumps([n.model_dump() if hasattr(n, "model_dump") else n for n in update_data["nodes"]], ensure_ascii=False)
    if "output_mapping" in update_data and update_data["output_mapping"]:
        update_data["output_mapping"] = json.dumps({k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in update_data["output_mapping"].items()}, ensure_ascii=False)
    if "actions" in update_data and update_data["actions"]:
        # 注入危险等级
        update_data["actions"] = json.dumps(
            _inject_severity(update_data["actions"], request.severity or "medium"),
            ensure_ascii=False
        )
    
    for field, value in update_data.items():
        setattr(rule, field, value)
    
    db.commit()
    db.refresh(rule)
    
    # TODO: Update scheduler
    
    return Response(msg="规则更新成功", data=_rule_to_response(rule))


@router.delete("/{rule_id}", response_model=Response)
async def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete rule"""
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return Response(code=404, msg="规则不存在")
    
    # TODO: Remove from scheduler
    
    db.delete(rule)
    db.commit()
    
    return Response(msg="删除成功")


@router.post("/{rule_id}/run", response_model=Response)
async def run_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
            except:
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
    current_user: User = Depends(get_current_user)
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
        # Add rule metadata to actions for create_alert
        for act in actions:
            if act.get("type") == "create_alert":
                act["_rule_id"] = rule.id
                act["_rule_name"] = rule.name
                act["_rule_severity"] = getattr(rule, "severity", "medium")
        executor = RuleExecutor(db)
        written = executor.process_actions(actions, results)
        rule.last_run = datetime.now()
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
