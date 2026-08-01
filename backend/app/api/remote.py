"""
自定义 API 接收接口（被动推送架构）

- 页面可定义多个接收接口，每个接口有名称（name）
- 源端（孤岛/不可直连服务器）只需往 POST /api/remote/ingest/{name} 发送数据，后端自动接收存储
- 接收接口列表与管理需登录；ingest 接收端点无需登录（源端无法登录，靠接口名称隐式标识）
"""
import json
import re

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, validator

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.base import get_db
from app.models.user import User
from app.models.ingest_endpoint import IngestEndpoint
from app.models.ingest_log import IngestLog
from app.api.security import get_current_user
from app.schemas.common import Response

router = APIRouter(tags=['remote-ingest'])

NAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class EndpointCreate(BaseModel):
    name: str
    description: str = ''

    @validator('name')
    def _validate_name(cls, v):
        if not NAME_RE.match(v or ''):
            raise ValueError('接口名称只能包含字母、数字、下划线和横线，长度 1-64')
        return v


class EndpointUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @validator('name')
    def _validate_name(cls, v):
        if v is not None and not NAME_RE.match(v):
            raise ValueError('接口名称只能包含字母、数字、下划线和横线，长度 1-64')
        return v


@router.post('/remote/endpoints', response_model=Response)
def create_endpoint(body: EndpointCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(IngestEndpoint).filter(IngestEndpoint.name == body.name).first():
        return Response(code=1, msg='接口名称已存在')
    ep = IngestEndpoint(name=body.name, description=body.description)
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return Response(code=0, msg='ok', data={'id': ep.id, 'name': ep.name, 'description': ep.description})


@router.get('/remote/endpoints', response_model=Response)
def list_endpoints(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    eps = db.query(IngestEndpoint).order_by(IngestEndpoint.id.desc()).all()
    items = []
    for ep in eps:
        cnt = db.query(func.count(IngestLog.id)).filter(IngestLog.endpoint_id == ep.id).scalar() or 0
        items.append({
            'id': ep.id,
            'name': ep.name,
            'description': ep.description,
            'count': cnt,
            'created_at': ep.created_at.strftime('%Y-%m-%d %H:%M:%S') if ep.created_at else '',
        })
    return Response(code=0, msg='ok', data=items)


@router.put('/remote/endpoints/{endpoint_id}', response_model=Response)
def update_endpoint(endpoint_id: int, body: EndpointUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=1, msg='接口不存在')
    if body.name is not None and body.name != ep.name:
        if db.query(IngestEndpoint).filter(IngestEndpoint.name == body.name, IngestEndpoint.id != endpoint_id).first():
            return Response(code=1, msg='接口名称已存在')
        ep.name = body.name
    if body.description is not None:
        ep.description = body.description
    db.commit()
    return Response(code=0, msg='ok', data={'id': ep.id, 'name': ep.name, 'description': ep.description})


@router.delete('/remote/endpoints/{endpoint_id}', response_model=Response)
def delete_endpoint(endpoint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=1, msg='接口不存在')
    db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.delete(ep)
    db.commit()
    return Response(code=0, msg='ok')


@router.delete('/remote/endpoints/{endpoint_id}/logs', response_model=Response)
def clear_logs(endpoint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """清空指定接口的全部接收数据"""
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=1, msg='接口不存在')
    db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id).delete()
    db.commit()
    return Response(code=0, msg='ok', data={'deleted': endpoint_id})


@router.delete('/remote/logs/{log_id}', response_model=Response)
def delete_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除单条接收数据"""
    log = db.query(IngestLog).filter(IngestLog.id == log_id).first()
    if not log:
        return Response(code=1, msg='数据不存在')
    db.delete(log)
    db.commit()
    return Response(code=0, msg='ok')


@router.post('/remote/ingest/{name}')
async def ingest(name: str, request: Request, db: Session = Depends(get_db)):
    """源端推送入口：无需登录，POST 任意数据到 /api/remote/ingest/{name} 即自动存储"""
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.name == name).first()
    if not ep:
        return Response(code=1, msg='接口不存在')
    try:
        raw = await request.body()
        text = raw.decode('utf-8', errors='replace') if raw else ''
    except Exception:
        text = ''
    log = IngestLog(endpoint_id=ep.id, endpoint_name=ep.name, payload=text)
    db.add(log)
    db.commit()
    db.refresh(log)
    return Response(code=0, msg='received', data={'id': log.id})


@router.get('/remote/endpoints/{endpoint_id}/logs', response_model=Response)
def list_logs(endpoint_id: int, page: int = 1, page_size: int = 20,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ep = db.query(IngestEndpoint).filter(IngestEndpoint.id == endpoint_id).first()
    if not ep:
        return Response(code=1, msg='接口不存在')
    q = db.query(IngestLog).filter(IngestLog.endpoint_id == endpoint_id)
    total = q.count()
    logs = q.order_by(IngestLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [{
        'id': l.id,
        'payload': l.payload,
        'received_at': l.received_at.strftime('%Y-%m-%d %H:%M:%S') if l.received_at else '',
    } for l in logs]
    return Response(code=0, msg='ok', data={'items': items, 'total': total})
