"""
Raw Log Query API - ES原始日志查询
"""
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.common import Response
from app.api.security import get_current_user
from app.services.es_service import ESService, ESConfig

router = APIRouter(prefix="/raw-logs", tags=["RawLogs"])


class QueryCondition(BaseModel):
    field: str
    operator: str
    value: Optional[str] = None


class RawLogQuery(BaseModel):
    conditions: Optional[List[QueryCondition]] = None
    logic: str = "AND"
    dsl: Optional[str] = None  # Lucene 语法查询
    time_range: str = "1h"
    page: int = 1
    page_size: int = 50


def _get_es_config(db: Session) -> ESConfig:
    cfg_keys = ["es_host", "es_port", "es_scheme", "es_verify_certs", "es_user", "es_password", "es_index"]
    cfg_values = {}
    for key in cfg_keys:
        cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        cfg_values[key] = cfg.value if cfg else ""
    return ESConfig(
        host=cfg_values.get("es_host", "localhost"),
        port=int(cfg_values.get("es_port", "9200") or "9200"),
        scheme=cfg_values.get("es_scheme", "https"),
        verify_certs=str(cfg_values.get("es_verify_certs", "false")).lower() == "true",
        user=cfg_values.get("es_user", ""),
        password=cfg_values.get("es_password", ""),
        default_index=cfg_values.get("es_index", "security-logs-*")
    )


def _build_time_range(time_range: str):
    """返回 ES 查询用的时间范围，支持 today 和相对时间"""
    if time_range == "today":
        from datetime import datetime, timezone
        # ES indexes UTC. "today" here means the UTC day boundary.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"gte": today_start.isoformat() + "Z"}
    mapping = {
        "1h": {"hours": 1},
        "6h": {"hours": 6},
        "24h": {"hours": 24},
        "7d": {"days": 7},
        "30d": {"days": 30},
    }
    return mapping.get(time_range, {"hours": 24})


def _build_condition_clause(cond: QueryCondition) -> dict:
    field = cond.field
    op = cond.operator
    value = cond.value

    # 全字段泛查询
    if field == "_all":
        if op in ("equals", "contains"):
            return {"query_string": {"query": f"*{value}*"}}
        elif op in ("not_equals", "not_contains"):
            return {"bool": {"must_not": [{"query_string": {"query": f"*{value}*"}}]}}

    if op == "equals":
        return {"term": {field: value}}
    elif op == "not_equals":
        return {"bool": {"must_not": [{"term": {field: value}}]}}
    elif op == "contains":
        return {"wildcard": {field: f"*{value}*"}}
    elif op == "not_contains":
        return {"bool": {"must_not": [{"wildcard": {field: f"*{value}*"}}]}}
    elif op == "gt":
        return {"range": {field: {"gt": value}}}
    elif op == "gte":
        return {"range": {field: {"gte": value}}}
    elif op == "lt":
        return {"range": {field: {"lt": value}}}
    elif op == "lte":
        return {"range": {field: {"lte": value}}}
    elif op == "exists":
        return {"exists": {"field": field}}
    elif op == "not_exists":
        return {"bool": {"must_not": [{"exists": {"field": field}}]}}
    else:
        return {"term": {field: value}}


@router.post("/query", response_model=Response)
async def query_raw_logs(
    request: RawLogQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询ES原始日志 - 支持可视化条件和Lucene语法"""
    try:
        config = _get_es_config(db)
        es = ESService(config=config)

        # 时间过滤
        time_window = _build_time_range(request.time_range)
        if isinstance(time_window, dict) and "gte" in time_window:
            time_clauses = [{"range": {"@timestamp": time_window}}]
        else:
            time_clauses = es._build_time_filter(time_window)

        # 构建查询
        if request.dsl:
            # Lucene 语法查询
            body = {
                "size": request.page_size,
                "from": (request.page - 1) * request.page_size,
                "query": {
                    "bool": {
                        "must": [
                            {"query_string": {"query": request.dsl}},
                            *time_clauses
                        ]
                    }
                },
                "sort": [{"@timestamp": {"order": "desc"}}],
                "track_total_hits": True
            }
        elif request.conditions:
            # 可视化条件查询
            must_clauses = list(time_clauses)

            if request.logic == "AND":
                for cond in request.conditions:
                    # _build_condition_clause 对否定操作符已经返回自带
                    # bool.must_not 的子句。这里必须放进 must —— 早先把
                    # _all 的否定再塞进 must_not 会双重否定，变成匹配命中集。
                    must_clauses.append(_build_condition_clause(cond))
            else:
                should_clauses = [_build_condition_clause(c) for c in request.conditions]
                must_clauses.append({"bool": {"should": should_clauses, "minimum_should_match": 1}})

            body = {
                "size": request.page_size,
                "from": (request.page - 1) * request.page_size,
                "query": {"bool": {"must": must_clauses}},
                "sort": [{"@timestamp": {"order": "desc"}}],
                "track_total_hits": True
            }
        else:
            return Response(code=400, msg="请提供查询条件")

        result = es.client.search(index=config.default_index, body=body)

        hits = result.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        records = [hit["_source"] for hit in hits.get("hits", [])]

        return Response(data={
            "total": total,
            "records": records,
            "page": request.page,
            "page_size": request.page_size,
            # ES 自己的查询耗时（毫秒）。前端不再用 Date.now() 差值冒充服务端耗时。
            "took": result.get("took"),
        })

    except Exception as e:
        err = str(e)
        # 提取 ES 的具体错误信息
        if "root_cause" in err:
            try:
                import re
                m = re.search(r'"reason":"(.*?)"', err)
                if m:
                    err = m.group(1)
            except Exception:
                pass
        return Response(code=500, msg=f"查询失败: {err}")


@router.get("/fields", response_model=Response)
async def get_available_fields(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取可用的查询字段"""
    fields = [
        # 访问日志字段
        {"field": "src_ip", "label": "源IP", "type": "string"},
        {"field": "request_method", "label": "请求方法", "type": "string"},
        {"field": "request_url", "label": "请求URL", "type": "string"},
        {"field": "request_status", "label": "状态码", "type": "number"},
        {"field": "request_leng", "label": "请求长度", "type": "number"},
        # 错误日志字段
        {"field": "server_name", "label": "域名", "type": "string"},
        {"field": "log_level", "label": "日志级别", "type": "string"},
        {"field": "pid", "label": "进程ID", "type": "string"},
        {"field": "error_msg", "label": "错误信息", "type": "string"},
        {"field": "request", "label": "完整请求", "type": "string"},
        # 通用字段
        {"field": "log_time", "label": "日志时间", "type": "string"},
        {"field": "@timestamp", "label": "时间戳", "type": "string"},
    ]
    return Response(data=fields)
