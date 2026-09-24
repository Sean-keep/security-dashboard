"""
自定义 API 接收接口（被动推送架构）

- 页面可定义多个接收接口，每个接口有名称（name）
- 源端 POST /api/remote/ingest/{name} 推数据。``X-Ingest-Token`` **可选** ——
  远程端脚本已经写死不能改，不带 token 也收
- 收下来的数据给日报用。身份靠接收端从第一包特征里认（源 IP / User-Agent /
  Content-Type / 载荷形状），管理员可以手动绑定起名字 —— 特征是提示不是凭证。
  绑定只是标注，日报勾了接口就要它最近一条，跟绑定无关
- 接收接口管理需登录；ingest 端点有大小/频率限制
"""
import hashlib
import json
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
from app.models.ingest_sender import IngestSender
from app.api.security import get_current_user
from app.core.permissions import require_permission
from app.schemas.common import Response
from app.utils.timezone import local_now

router = APIRouter(tags=["remote-ingest"])

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# In-process sliding-window rate limiter for the unauthenticated ingest path.
# Good enough for a single uvicorn worker; swap for Redis if you scale out.
_INGEST_HITS: dict = defaultdict(deque)


def _ingest_rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = _INGEST_HITS[key]
    cutoff = now - 60.0
    while window and window[0] < cutoff:
        window.popleft()
    limit = settings.INGEST_RATE_LIMIT_PER_MINUTE
    limited = len(window) >= limit
    if not limited:
        # 被拒的那次不占额度，但放行的这次一定要计数 —— 早先这里有个分支
        # 直接 return False 漏了 append，等于每分钟第一条免费。
        window.append(now)
    # 顺手回收早已空置的 key，否则每个用过的接口名都永久占一个 deque
    for empty_key in [k for k, w in _INGEST_HITS.items() if not w]:
        _INGEST_HITS.pop(empty_key, None)
    return limited


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
        # 存活信号：没有它就分不清「agent 挂了」和「本来就没数据」
        "last_received_at": ep.last_received_at.strftime("%Y-%m-%d %H:%M:%S") if ep.last_received_at else "",
    }
    if ep.last_received_at:
        data["seconds_since_last"] = int((local_now() - ep.last_received_at).total_seconds())
    else:
        data["seconds_since_last"] = None
    if count is not None:
        data["count"] = count
    return data


def _rotate_token(ep: IngestEndpoint) -> str:
    token = secrets.token_urlsafe(32)
    ep.token = token
    return token


def _payload_shape(text: str) -> str:
    """载荷顶层字段名，给管理员当识别提示。

    这不是凭证 —— 对方照抄一份就能伪造出同样的形状。存在这里只是为了绑定时
    能一眼看出「这堆和那堆不是同一个东西」。
    """
    if not text or not text.strip():
        return "empty"
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return "non-json"
    if isinstance(obj, dict):
        return ",".join(sorted(str(k) for k in obj.keys()))[:256]
    return type(obj).__name__


def _sender_fingerprint(src_ip: str, user_agent: str, content_type: str, shape: str) -> str:
    raw = f"{src_ip}|{user_agent}|{content_type}|{shape}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def _sender_dict(s: IngestSender) -> dict:
    return {
        "id": s.id,
        "endpoint_id": s.endpoint_id,
        "endpoint_name": s.endpoint_name or "",
        "fingerprint": s.fingerprint,
        "src_ip": s.src_ip or "",
        "user_agent": s.user_agent or "",
        "content_type": s.content_type or "",
        "payload_shape": s.payload_shape or "",
        "display_name": s.display_name or "",
        "status": s.status or "pending",
        "sample_payload": s.sample_payload or "",
        "send_count": int(s.send_count or 0),
        "first_seen_at": s.first_seen_at.strftime("%Y-%m-%d %H:%M:%S") if s.first_seen_at else "",
        "last_seen_at": s.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if s.last_seen_at else "",
        "bound_at": s.bound_at.strftime("%Y-%m-%d %H:%M:%S") if s.bound_at else "",
    }


@router.post("/remote/endpoints", response_model=Response)
def create_endpoint(
    body: EndpointCreate,
    db: Session = Depends(get_db),
    # 铸造数据源凭据 = 授权行为，不能只要「登录了」就能做
    user: User = Depends(require_permission("manage_system")),
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
    # 轮换会让正当源立刻断供 —— 必须 admin
    user: User = Depends(require_permission("manage_system")),
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
    user: User = Depends(require_permission("manage_system")),
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
    user: User = Depends(require_permission("manage_system")),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.query(IngestSender).filter(IngestSender.endpoint_id == endpoint_id).delete()
    db.delete(ep)
    db.commit()
    return Response(msg="ok")


@router.delete("/remote/endpoints/{endpoint_id}/logs", response_model=Response)
def clear_logs(
    endpoint_id: int,
    db: Session = Depends(get_db),
    # 清日志是反取证动作
    user: User = Depends(require_permission("manage_system")),
):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=404, msg="接口不存在")
    deleted = db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.commit()
    return Response(msg="ok", data={"deleted": deleted})


@router.delete("/remote/logs/{log_id}", response_model=Response)
def delete_log(
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("manage_system")),
):
    log = db.query(IngestLog).filter(IngestLog.id == log_id).first()
    if not log:
        return Response(code=404, msg="数据不存在")
    db.delete(log)
    db.commit()
    return Response(msg="ok")


def _parse_sent_at(raw: Optional[str]) -> Optional[datetime]:
    """X-Sent-At → naive local datetime（库内时间戳一律 naive local）。"""
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        # 源端给了时区就换算到本机本地；库内是 naive local
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


@router.post("/remote/ingest/{name}")
async def ingest(
    name: str,
    request: Request,
    db: Session = Depends(get_db),
    x_ingest_token: Optional[str] = Header(default=None, alias="X-Ingest-Token"),
    x_message_id: Optional[str] = Header(default=None, alias="X-Message-Id"),
    x_sent_at: Optional[str] = Header(default=None, alias="X-Sent-At"),
):
    """源端推送入口。

    认证：``X-Ingest-Token`` **可选**。带了且接口配了密钥就校验；不带就直接收 ——
    远程端脚本已经写死，不能指望它带头。

    限制：body ≤ INGEST_MAX_BODY_BYTES，每分钟 ≤ INGEST_RATE_LIMIT_PER_MINUTE 次。

    幂等：带 ``X-Message-Id`` 的重投会命中已有行并原样返回，不再插重复数据 ——
    推送端遇到 429/5xx 必然重试，没有这个键就是重复行 + 计数虚高。
    时序：``X-Sent-At`` 记录源端发送时间；接收端的 id/received_at 只反映到达顺序，
    重试送达的旧批次会排在新批次后面。
    """
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.name == name).first()
    if not ep:
        # Do not distinguish "no such endpoint" from "bad token" beyond this —
        # the name is already in the URL, so a 404 here is not an oracle.
        raise HTTPException(status_code=404, detail="接口不存在")

    # token 从「必须」降级成「可选额外锁」：远程端脚本不动，不带头也收。
    # 带了但对不上仍然拒 —— 一旦用上了就不能默默放行错误密钥。
    provided = (x_ingest_token or "").strip()
    if provided and ep.token and not secrets.compare_digest(provided, ep.token):
        raise HTTPException(status_code=401, detail="推送密钥无效")

    if _ingest_rate_limited(ep.name):
        # 让重试的源端知道该等多久，否则它会立刻重投并撞出重复行
        raise HTTPException(
            status_code=429,
            detail="推送过于频繁，请稍后再试",
            headers={"Retry-After": "60"},
        )

    # content-length 只是快路径预检；chunked 上传没有这个头，或者值会撒谎。
    # 真正的上限必须在流式读取时执行 —— 早先 `await request.body()` 是先把整个
    # body 读进内存再判大小，等于给这条无鉴权路径开了一个内存 DoS。
    limit = settings.INGEST_MAX_BODY_BYTES
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        raise HTTPException(status_code=413, detail="推送数据过大")

    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(status_code=413, detail="推送数据过大")

    text = bytes(raw).decode("utf-8", errors="replace") if raw else ""

    # 第一包特征 → 发送方指纹。同一 (接口, 指纹) 归成一个发送方，管理员只认一次。
    now = local_now()
    src_ip = ((request.client.host if request.client else "") or "").strip()[:64]
    user_agent = (request.headers.get("user-agent") or "")[:256]
    content_type = (request.headers.get("content-type") or "")[:128]
    shape = _payload_shape(text)
    fp = _sender_fingerprint(src_ip, user_agent, content_type, shape)

    sender = (
        db.query(IngestSender)
        .filter(IngestSender.endpoint_id == ep.id, IngestSender.fingerprint == fp)
        .first()
    )
    if sender is None:
        sender = IngestSender(
            endpoint_id=ep.id,
            endpoint_name=ep.name,
            fingerprint=fp,
            src_ip=src_ip,
            user_agent=user_agent,
            content_type=content_type,
            payload_shape=shape,
            status="pending",
            sample_payload=text[:2000],
            send_count=0,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(sender)
        db.flush()

    message_id = (x_message_id or "").strip()[:128]
    if message_id:
        existing = (
            db.query(IngestLog)
            .filter(IngestLog.endpoint_id == ep.id, IngestLog.message_id == message_id)
            .first()
        )
        if existing:
            return Response(msg="duplicate", data={"id": existing.id, "duplicate": True})

    try:
        log = IngestLog(
            endpoint_id=ep.id,
            endpoint_name=ep.name,
            sender_id=sender.id if sender else None,
            payload=text,
            message_id=message_id or None,
            sent_at=_parse_sent_at(x_sent_at),
        )
        ep.last_received_at = now
        if sender:
            sender.send_count = int(sender.send_count or 0) + 1
            sender.last_seen_at = now
        db.add(log)
        db.commit()
    except Exception:
        # 幂等键撞车（并发重投）由唯一索引兜底 —— 那不是错误，是重复投递
        db.rollback()
        if message_id:
            existing = (
                db.query(IngestLog)
                .filter(IngestLog.endpoint_id == ep.id, IngestLog.message_id == message_id)
                .first()
            )
            if existing:
                return Response(msg="duplicate", data={"id": existing.id, "duplicate": True})
        raise
    db.refresh(log)
    # 始终 200：远程端脚本写死了，不能靠状态码让它改行为。
    return Response(
        msg="received",
        data={
            "id": log.id,
            "duplicate": False,
            "sender_id": sender.id if sender else None,
            "sender_status": (sender.status if sender else "pending") or "pending",
        },
    )


class SenderBindRequest(BaseModel):
    """绑定：起个名字，标记为「认了」。纯标注，不改变日报取数。"""
    display_name: str = ""


@router.get("/remote/senders", response_model=Response)
def list_senders(
    endpoint_id: int = Query(default=0),
    status: str = Query(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发送方列表（按第一包特征聚出来）。只读，任意登录角色可看。"""
    q = db.query(IngestSender)
    if endpoint_id:
        q = q.filter(IngestSender.endpoint_id == endpoint_id)
    if status:
        q = q.filter(IngestSender.status == status)
    items = [_sender_dict(s) for s in q.order_by(IngestSender.last_seen_at.desc()).all()]
    return Response(msg="ok", data={"items": items, "total": len(items)})


@router.post("/remote/senders/{sender_id}/bind", response_model=Response)
def bind_sender(
    sender_id: int,
    body: SenderBindRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("manage_system", "operate")),
):
    """认人：给这个发送方起个名字。"""
    s = db.query(IngestSender).filter(IngestSender.id == sender_id).first()
    if not s:
        return Response(code=404, msg="发送方不存在")
    name = (body.display_name or "").strip()[:128]
    s.display_name = name or s.src_ip or f"sender-{s.id}"
    s.status = "bound"
    s.bound_at = local_now()
    db.commit()
    db.refresh(s)
    return Response(msg="ok", data=_sender_dict(s))


@router.post("/remote/senders/{sender_id}/reject", response_model=Response)
def reject_sender(
    sender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("manage_system", "operate")),
):
    """拒收：标成不要的。数据照存，日报照取接口最近一条。"""
    s = db.query(IngestSender).filter(IngestSender.id == sender_id).first()
    if not s:
        return Response(code=404, msg="发送方不存在")
    s.status = "rejected"
    db.commit()
    db.refresh(s)
    return Response(msg="ok", data=_sender_dict(s))


@router.post("/remote/senders/{sender_id}/unbind", response_model=Response)
def unbind_sender(
    sender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("manage_system", "operate")),
):
    """退回待绑定 —— 绑错了可以反悔。"""
    s = db.query(IngestSender).filter(IngestSender.id == sender_id).first()
    if not s:
        return Response(code=404, msg="发送方不存在")
    s.status = "pending"
    s.bound_at = None
    db.commit()
    db.refresh(s)
    return Response(msg="ok", data=_sender_dict(s))


@router.delete("/remote/senders/{sender_id}", response_model=Response)
def delete_sender(
    sender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("manage_system", "operate")),
):
    """删掉这个发送方的识别记录（它推过的数据保留，sender_id 置空）。"""
    s = db.query(IngestSender).filter(IngestSender.id == sender_id).first()
    if not s:
        return Response(code=404, msg="发送方不存在")
    db.query(IngestLog).filter(IngestLog.sender_id == sender_id).update({"sender_id": None})
    db.delete(s)
    db.commit()
    return Response(msg="ok")


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
    logs = (
        q.order_by(IngestLog.sent_at.desc(), IngestLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 一次查出这批日志归属的发送方，别一行一查
    sender_ids = {l.sender_id for l in logs if l.sender_id}
    senders = {
        s.id: s
        for s in db.query(IngestSender).filter(IngestSender.id.in_(sender_ids)).all()
    } if sender_ids else {}
    items = [{
        "id": l.id,
        "payload": l.payload,
        "message_id": l.message_id or "",
        "sent_at": l.sent_at.strftime("%Y-%m-%d %H:%M:%S") if l.sent_at else "",
        "received_at": l.received_at.strftime("%Y-%m-%d %H:%M:%S") if l.received_at else "",
        "sender_id": l.sender_id,
        "sender_name": (
            (senders[l.sender_id].display_name or senders[l.sender_id].src_ip)
            if l.sender_id in senders else ""
        ),
        "sender_status": senders[l.sender_id].status if l.sender_id in senders else "",
    } for l in logs]
    return Response(msg="ok", data={"items": items, "total": total, "page": page, "page_size": page_size})
