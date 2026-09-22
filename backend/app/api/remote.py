"""
自定义 API 接收接口（被动推送架构）

- 页面可定义多个接收接口，每个接口有名称（name）和密钥（token）
- 源端 POST /api/remote/ingest/{name}，请求头带 X-Ingest-Token
- 接收接口管理需登录；ingest 端点靠 token 认证（源端无法登录），且有大小/频率限制
"""
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import get_db
from app.models.user import User
from app.models.ingest_endpoint import IngestEndpoint
from app.models.ingest_log import IngestLog
from app.api.security import get_current_user
from app.schemas.common import Response

router = APIRouter(tags=["remote-ingest"])

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# In-process sliding-window rate limiter for the unauthenticated ingest path.
# Good enough for a single uvicorn worker; swap for Redis if you scale out.
_INGEST_HITS: dict = defaultdict(deque)
_INGEST_LOCK = object()  # placeholder to keep the module self-describing


def _ingest_rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = _INGEST_HITS[key]
    cutoff = now - 60.0
    while window and window[0] < cutoff:
        window.popleft()
    limit = settings.INGEST_RATE_LIMIT_PER_MINUTE
    if len(window) >= limit:
        return True
    window.append(now)
    return False


class EndpointCreate(BaseModel):
    name: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not NAME_RE.match(v or ""):
            raise ValueError("接口名称只能包含字母、数字、下划线和横线，长度 1-64")
        return v


class EndpointUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not NAME_RE.match(v):
            raise ValueError("接口名称只能包含字母、数字、下划线和横线，长度 1-64")
        return v


def _public_dict(ep: IngestEndpoint, count: Optional[int] = None) -> dict:
    data = {
        "id": ep.id,
        "name": ep.name,
        "description": ep.description or "",
        "created_at": ep.created_at.strftime("%Y-%m-%d %H:%M:%S") if ep.created_at else "",
    }
    if count is not None:
        data["count"] = count
    return data


def _rotate_token(ep: IngestEndpoint) -> str:
    token = secrets.token_urlsafe(32)
    ep.token = token
    return token


@router.post("/remote/endpoints", response_model=Response)
def create_endpoint(
    body: EndpointCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.query(IngestEndpoint).filter(IngestEndpoint.name == body.name).first():
        return Response(code=409, msg="接口名称已存在")
    ep = IngestEndpoint(name=body.name, description=body.description)
    token = _rotate_token(ep)
    db.add(ep)
    db.commit()
    db.refresh(ep)
    data = _public_dict(ep)
    data["token"] = token  # shown once at creation; store it on the source side
    return Response(msg="ok", data=data)


@router.get("/remote/endpoints", response_model=Response)
def list_endpoints(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    eps = db.query(IngestEndpoint).order_by(IngestEndpoint.id.desc()).all()
    # Single GROUP BY instead of one COUNT per endpoint.
    counts = dict(
        db.query(IngestLog.endpoint_id, func.count(IngestLog.id))
        .group_by(IngestLog.endpoint_id)
        .all()
    )
    items = []
    for ep in eps:
        d = _public_dict(ep, count=counts.get(ep.id, 0))
        # Never echo the token in a list response — only its presence.
        d["has_token"] = bool(ep.token)
        items.append(d)
    return Response(msg="ok", data=items)


@router.post("/remote/endpoints/{endpoint_id}/rotate-token", response_model=Response)
def rotate_token(
    endpoint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    token = _rotate_token(ep)
    db.commit()
    return Response(msg="ok", data={"id": ep.id, "token": token})


@router.put("/remote/endpoints/{endpoint_id}", response_model=Response)
def update_endpoint(
    endpoint_id: int,
    body: EndpointUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    if body.name is not None and body.name != ep.name:
        if db.query(IngestEndpoint).filter(
            IngestEndpoint.name == body.name, IngestEndpoint.id != endpoint_id
        ).first():
            return Response(code=409, msg="接口名称已存在")
        ep.name = body.name
    if body.description is not None:
        ep.description = body.description
    db.commit()
    return Response(msg="ok", data=_public_dict(ep))


@router.delete("/remote/endpoints/{endpoint_id}", response_model=Response)
def delete_endpoint(
    endpoint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.delete(ep)
    db.commit()
    return Response(msg="ok")


@router.delete("/remote/endpoints/{endpoint_id}/logs", response_model=Response)
def clear_logs(
    endpoint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    deleted = db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.commit()
    return Response(msg="ok", data={"deleted": deleted})


@router.delete("/remote/logs/{log_id}", response_model=Response)
def delete_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    log = db.query(IngestLog).filter(IngestLog.id == log_id).first()
    if not log:
        return Response(code=404, msg="数据不存在")
    db.delete(log)
    db.commit()
    return Response(msg="ok")


@router.post("/remote/ingest/{name}")
async def ingest(
    name: str,
    request: Request,
    db: Session = Depends(get_db),
    x_ingest_token: Optional[str] = Header(default=None, alias="X-Ingest-Token"),
):
    """源端推送入口。

    认证：请求头 ``X-Ingest-Token`` 必须与该接口的 token 一致。
    限制：body ≤ INGEST_MAX_BODY_BYTES，每分钟 ≤ INGEST_RATE_LIMIT_PER_MINUTE 次。
    """
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.name == name).first()
    if not ep:
        # Do not distinguish "no such endpoint" from "bad token" beyond this —
        # the name is already in the URL, so a 404 here is not an oracle.
        raise HTTPException(status_code=404, detail="接口不存在")

    if not ep.token:
        raise HTTPException(status_code=403, detail="该接口未配置推送密钥，请先轮换生成")

    provided = (x_ingest_token or "").strip()
    if not provided or not secrets.compare_digest(provided, ep.token):
        raise HTTPException(status_code=401, detail="推送密钥无效")

    if _ingest_rate_limited(ep.name):
        raise HTTPException(status_code=429, detail="推送过于频繁，请稍后再试")

    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > settings.INGEST_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="推送数据过大")

    raw = await request.body()
    if len(raw) > settings.INGEST_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="推送数据过大")

    text = raw.decode("utf-8", errors="replace") if raw else ""
    log = IngestLog(endpoint_id=ep.id, endpoint_name=ep.name, payload=text)
    db.add(log)
    db.commit()
    db.refresh(log)
    return Response(msg="received", data={"id": log.id})


@router.get("/remote/endpoints/{endpoint_id}/logs", response_model=Response)
def list_logs(
    endpoint_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    q = db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id)
    total = q.count()
    logs = q.order_by(IngestLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [{
        "id": l.id,
        "payload": l.payload,
        "received_at": l.received_at.strftime("%Y-%m-%d %H:%M:%S") if l.received_at else "",
    } for l in logs]
    return Response(msg="ok", data={"items": items, "total": total, "page": page, "page_size": page_size})
