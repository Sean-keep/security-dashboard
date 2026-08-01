"""
远程孤岛执行 API（反向推送架构）
- 后端不主动连接目标服务器（孤岛不可达）
- 目标服务器主动 POST 结果到 /api/remote/results（用 token 鉴权）
- 后端生成自包含采集器脚本，用户在孤岛运行，结果自动回传
"""
import json
import secrets

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.models.base import get_db, Base, engine
from app.models.user import User
from app.models.script import Script
from app.models.remote_host import RemoteHost
from app.models.remote_execution import RemoteExecution
from app.schemas.common import Response
from app.api.security import get_current_user

router = APIRouter(prefix="/api/remote", tags=["Remote"])

Base.metadata.create_all(bind=engine)


# ── Pydantic ──────────────────────────────────────────────────────────────
class HostCreate(BaseModel):
    alias: str


class HostUpdate(BaseModel):
    alias: str


class ResultPush(BaseModel):
    token: str
    host_alias: str = ""
    script_id: Optional[int] = None
    script_name: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


# ── 采集器模板（python）─────────────────────────────────────────────────────
COLLECTOR_TMPL = '''#!/usr/bin/env python3
# 自动生成的远程采集器 - 请勿手动修改
import urllib.request, json, sys, subprocess

CALLBACK_URL = {callback}
TOKEN = {token}
HOST_ALIAS = {alias}
SCRIPT_ID = {script_id}
LANG = {lang}
SCRIPT_CONTENT = {content}

def run():
    if LANG == 'python':
        p = subprocess.run([sys.executable, '-c', SCRIPT_CONTENT], capture_output=True, timeout=300)
    else:
        p = subprocess.run(['bash', '-c', SCRIPT_CONTENT], capture_output=True, timeout=300)
    return {{
        'token': TOKEN,
        'host_alias': HOST_ALIAS,
        'script_id': SCRIPT_ID,
        'script_name': '',
        'stdout': p.stdout.decode('utf-8', 'replace'),
        'stderr': p.stderr.decode('utf-8', 'replace'),
        'exit_code': p.returncode,
    }}

if __name__ == '__main__':
    data = run()
    req = urllib.request.Request(CALLBACK_URL, data=json.dumps(data).encode(), headers={{'Content-Type': 'application/json'}})
    try:
        urllib.request.urlopen(req, timeout=30)
        print('OK: result pushed')
    except Exception as e:
        print('ERR: push failed:', e)
'''


# ── 主机管理（需登录）────────────────────────────────────────────────────────
@router.post("/hosts")
def create_host(body: HostCreate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    alias = (body.alias or "").strip()
    if not alias:
        return Response(code=400, msg="别名不能为空")
    if db.query(RemoteHost).filter(RemoteHost.alias == alias).first():
        return Response(code=400, msg="别名已存在")
    token = secrets.token_hex(24)
    h = RemoteHost(alias=alias, token=token, created_by=current_user.username)
    db.add(h)
    db.commit()
    db.refresh(h)
    return Response(data={"id": h.id, "alias": h.alias, "token": h.token})


@router.get("/hosts")
def list_hosts(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    rows = db.query(RemoteHost).order_by(RemoteHost.id.desc()).all()
    items = [{
        "id": r.id, "alias": r.alias, "token": r.token,
        "last_seen": r.last_seen.strftime("%Y-%m-%d %H:%M:%S") if r.last_seen else "",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
    } for r in rows]
    return Response(data=items)


@router.put("/hosts/{host_id}")
def update_host(host_id: int, body: HostUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    h = db.query(RemoteHost).filter(RemoteHost.id == host_id).first()
    if not h:
        return Response(code=404, msg="主机不存在")
    alias = (body.alias or "").strip()
    if not alias:
        return Response(code=400, msg="别名不能为空")
    if db.query(RemoteHost).filter(RemoteHost.alias == alias, RemoteHost.id != host_id).first():
        return Response(code=400, msg="别名已存在")
    h.alias = alias
    db.commit()
    return Response(msg="已更新")


@router.post("/hosts/{host_id}/reset-token")
def reset_token(host_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    h = db.query(RemoteHost).filter(RemoteHost.id == host_id).first()
    if not h:
        return Response(code=404, msg="主机不存在")
    h.token = secrets.token_hex(24)
    db.commit()
    return Response(data={"id": h.id, "token": h.token})


@router.delete("/hosts/{host_id}")
def delete_host(host_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    h = db.query(RemoteHost).filter(RemoteHost.id == host_id).first()
    if not h:
        return Response(code=404, msg="主机不存在")
    db.delete(h)
    db.commit()
    return Response(msg="已删除")


# ── 接收孤岛推送（token 鉴权，无需登录）─────────────────────────────────────────
@router.post("/results")
def receive_result(body: ResultPush, db: Session = Depends(get_db)):
    h = db.query(RemoteHost).filter(RemoteHost.token == body.token).first()
    if not h:
        return Response(code=401, msg="token 无效")
    h.last_seen = datetime.now()
    rec = RemoteExecution(
        host_id=h.id,
        host_alias=h.alias,
        script_id=body.script_id,
        script_name=body.script_name or "",
        stdout=body.stdout or "",
        stderr=body.stderr or "",
        exit_code=body.exit_code or 0,
        received_at=datetime.now(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return Response(data={"id": rec.id})


# ── 执行结果列表（需登录）──────────────────────────────────────────────────────
@router.get("/executions")
def list_executions(page: int = Query(default=1, ge=1),
                    page_size: int = Query(default=20, ge=1, le=200),
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    total = db.query(RemoteExecution).count()
    rows = (
        db.query(RemoteExecution)
        .order_by(RemoteExecution.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [{
        "id": r.id, "host_id": r.host_id, "host_alias": r.host_alias,
        "script_id": r.script_id, "script_name": r.script_name,
        "exit_code": r.exit_code,
        "received_at": r.received_at.strftime("%Y-%m-%d %H:%M:%S") if r.received_at else "",
        "stdout_len": len(r.stdout or ""),
        "stderr_len": len(r.stderr or ""),
    } for r in rows]
    return Response(data={"total": total, "items": items, "page": page, "page_size": page_size})


@router.get("/executions/{exec_id}")
def get_execution(exec_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    r = db.query(RemoteExecution).filter(RemoteExecution.id == exec_id).first()
    if not r:
        return Response(code=404, msg="记录不存在")
    return Response(data={
        "id": r.id, "host_alias": r.host_alias, "script_id": r.script_id,
        "script_name": r.script_name, "exit_code": r.exit_code,
        "received_at": r.received_at.strftime("%Y-%m-%d %H:%M:%S") if r.received_at else "",
        "stdout": r.stdout or "", "stderr": r.stderr or "",
    })


# ── 生成采集器脚本（需登录）────────────────────────────────────────────────────
@router.get("/scripts/{script_id}/collector")
def generate_collector(script_id: int, host_id: int = Query(...),
                       callback_url: str = Query(...),
                       lang: str = Query(default="python"),
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    s = db.query(Script).filter(Script.id == script_id).first()
    if not s:
        return Response(code=404, msg="脚本不存在")
    h = db.query(RemoteHost).filter(RemoteHost.id == host_id).first()
    if not h:
        return Response(code=404, msg="主机不存在")
    cb = callback_url.rstrip("/") + "/api/remote/results"
    content = COLLECTOR_TMPL.format(
        callback=json.dumps(cb),
        token=json.dumps(h.token),
        alias=json.dumps(h.alias),
        script_id=script_id,
        lang=json.dumps(lang),
        content=json.dumps(s.content),
    )
    fname = "collector_%s_%s.py" % (h.alias, s.id)
    return Response(data={"filename": fname, "content": content})
