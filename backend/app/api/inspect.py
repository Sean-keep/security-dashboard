"""Inspection API - Scripts + Traffic + Metrics + VirusTotal"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import re

import os

import time

import subprocess

import urllib.request

import urllib.error

import urllib.parse

import json

from datetime import datetime, timedelta

from typing import List, Optional, Dict, Any, Union

from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from app.models.base import get_db, Base, engine

from app.models.user import User

from app.models.script import Script

from app.models.config import SystemConfig

from app.models.custom_metric import CustomMetric

from app.schemas.common import Response

from app.api.security import get_current_user

router = APIRouter(prefix="/api/inspect", tags=["Inspection"])

# Ensure tables are created when module loads

Base.metadata.create_all(bind=engine)

# ?? Helpers ???????????????????????????????????????????????????????????????????

DANGEROUS_IMPORTS = {

    'os', 'subprocess', 'shutil', 'importlib',

    'eval', 'exec', 'compile', 'open',

    'file', 'input', 'reload', '__import__'

}

def _check_script_safety(code: str) -> Optional[str]:

    """Return error message if script is dangerous, else None."""

    for imp in DANGEROUS_IMPORTS:

        patterns = [

            rf'\bimport\s+{imp}\b',

            rf'\bfrom\s+{imp}\b',

            rf'\b{imp}\s*\.',

        ]

        for p in patterns:

            if re.search(p, code):

                return f"禁?导入 {imp}，已拒绝执?"

    return None

def _run_script(code: str, lang: str, timeout: int = 30, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:

    """Execute script in sandbox. Returns {stdout, stderr, exit_code}."""

    err = _check_script_safety(code)

    if err:

        return {'stdout': '', 'stderr': err, 'exit_code': 1}

    run_env = os.environ.copy()

    if env:

        run_env.update(env)

    if lang == 'python':

        result = subprocess.run(

            ['python3', '-c', code],

            capture_output=True, timeout=timeout, env=run_env

        )

    else:

        result = subprocess.run(

            ['bash', '-c', code],

            capture_output=True, timeout=timeout, env=run_env

        )

    return {

        'stdout': result.stdout.decode('utf-8', errors='replace'),

        'stderr': result.stderr.decode('utf-8', errors='replace'),

        'exit_code': result.returncode

    }

def _get_es_service(db: Session):

    """Build ES service from config."""

    from app.services.es_service import ESService

    cfg_keys = ['es_host', 'es_port', 'es_scheme', 'es_verify_certs', 'es_user', 'es_password', 'es_index']

    cfg = {}

    for k in cfg_keys:

        row = db.query(SystemConfig).filter(SystemConfig.key == k).first()

        cfg[k] = row.value if row else ''

    return ESService(

        host=cfg.get('es_host', 'localhost'),

        port=int(cfg.get('es_port', 9200)),

        scheme=cfg.get('es_scheme', 'https'),

        verify_certs=cfg.get('es_verify_certs', 'false') == 'true',

        user=cfg.get('es_user', ''),

        password=cfg.get('es_password', ''),

        default_index=cfg.get('es_index', 'security-logs-*')

    )

def _get_ipinfo_country(ip: str) -> Optional[str]:

    """Query ipinfo.io for country (no API key needed). Returns 2-letter country code."""

    try:

        req = urllib.request.Request(

            f'https://ipinfo.io/{ip}/json',

            headers={'User-Agent': 'Mozilla/5.0 SecurityDashboard/1.0', 'Accept': 'application/json'}

        )

        with urllib.request.urlopen(req, timeout=8) as resp:

            data = json.loads(resp.read())

            return data.get('country', '') or None

    except Exception:

        return None

def _get_virustotal_info(ip: str, db: Session) -> Optional[Dict]:

    """Query VirusTotal for country info (fallback when ipinfo fails)."""

    api_key_row = db.query(SystemConfig).filter(SystemConfig.key == 'virustotal_api_key').first()

    api_key = api_key_row.value if api_key_row else ''

    if not api_key:

        return None

    try:

        req = urllib.request.Request(

            f'https://www.virustotal.com/api/v3/ip_addresses/{ip}',

            headers={'x-apikey': api_key, 'User-Agent': 'SecurityDashboard/1.0'}

        )

        with urllib.request.urlopen(req, timeout=5) as resp:

            data = json.loads(resp.read())

            country = data.get('data', {}).get('attributes', {}).get('country', '')

            return {'country': country}

    except Exception:

        return None

COUNTRY_MAP = {
    'CN': '中国', 'US': '美国', 'JP': '日本', 'KR': '韩国', 'SG': '新加坡',
    'HK': '中国香港', 'TW': '中国台湾', 'DE': '德国', 'FR': '法国', 'GB': '英国',
    'AU': '澳大利亚', 'CA': '加拿大', 'IN': '印度', 'RU': '俄罗斯', 'BR': '巴西',
    'NL': '荷兰', 'SE': '瑞典', 'CH': '瑞士', 'IT': '意大利', 'ES': '西班牙',
    'MX': '墨西哥', 'AR': '阿根廷', 'ZA': '南非', 'AE': '阿联酋', 'SA': '沙特阿拉伯',
    'TH': '泰国', 'VN': '越南', 'MY': '马来西亚', 'ID': '印度尼西亚', 'PH': '菲律宾',
    'NG': '尼日利亚', 'EG': '埃及', 'TR': '土耳其', 'PL': '波兰', 'CZ': '捷克',
    'NO': '挪威', 'DK': '丹麦', 'FI': '芬兰', 'PT': '葡萄牙', 'UA': '乌克兰',
    'IE': '爱尔兰', 'AT': '奥地利', 'BE': '比利时', 'CL': '智利', 'CO': '哥伦比亚',
    'PE': '秘鲁', 'NZ': '新西兰', 'RO': '罗马尼亚', 'HU': '匈牙利', 'BG': '保加利亚',
    'IL': '以色列', 'GR': '希腊', 'PK': '巴基斯坦', 'BD': '孟加拉国', 'NP': '尼泊尔',
    'MM': '缅甸', 'KH': '柬埔寨', 'LA': '老挝', 'BN': '文莱', 'MN': '蒙古',
}

def _to_chinese_country(code: str) -> str:

    return COUNTRY_MAP.get(code.upper(), code)

def _cfg_get(db, key, default=''):

    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()

    return row.value if row else default

def _grafana_headers(db):

    import base64

    auth_mode = _cfg_get(db, 'grafana_auth_mode', 'apikey')

    base_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    if auth_mode == 'basic':

        user = _cfg_get(db, 'grafana_user', '')

        pwd = _cfg_get(db, 'grafana_password', '')

        if user and pwd:

            token = base64.b64encode(f'{user}:{pwd}'.encode()).decode()

            return {**base_headers, 'Authorization': f'Basic {token}'}

    else:

        api_key = _cfg_get(db, 'grafana_api_key', '')

        if api_key:

            return {**base_headers, 'Authorization': f'Bearer {api_key}'}

    return base_headers

# ?? Pydantic Schemas ??????????????????????????????????????????????????????????

class ScriptCreate(BaseModel):

    name: str

    script_type: str = 'python'

    description: str = ''

    content: str

class ScriptUpdate(BaseModel):

    name: Optional[str] = None

    script_type: Optional[str] = None

    description: Optional[str] = None

    content: Optional[str] = None

    is_active: Optional[bool] = None

class ScriptExecRequest(BaseModel):

    script_ids: List[int]

    extra_env: Optional[Dict[str, str]] = {}

class AdhocExecRequest(BaseModel):

    type: str  # python | shell

    script: str

class BlockTarget(BaseModel):

    ip: str

    env: Optional[Dict[str, str]] = None

class BlockExecRequest(BaseModel):

    script_id: int

    targets: List[BlockTarget]

class TrafficQuery(BaseModel):

    index: Optional[str] = None

    window_minutes: int = 30

    group_by_field: str = 'domain'

    metric_field: str = 'request_uri'

    filters: Optional[List[Dict]] = None

class PipInstallReq(BaseModel):

    package: str

class PipUninstallReq(BaseModel):

    package: str

# ?直接?Dict[str, str]，不?要嵌?model（前?接发?dict?

class CustomMetricCreate(BaseModel):

    name: str = Field(..., max_length=128)

    description: str = Field(default="")

    promql: str = Field(...)

    unit: str = Field(default="")

class CustomMetricUpdate(BaseModel):

    name: Optional[str] = Field(default=None, max_length=128)

    description: Optional[str] = None

    promql: Optional[str] = None

    unit: Optional[str] = Field(default=None, max_length=32)

# ?? Script CRUD ??????????????????????????????????????????????????????????????

@router.get("/scripts", response_model=Response[List[dict]])

def list_scripts(db: Session = Depends(get_db)):

    rows = db.query(Script).order_by(Script.id.desc()).all()

    return Response(data=[{

        'id': s.id, 'name': s.name, 'script_type': s.script_type,

        'description': s.description, 'content': s.content,

        'is_active': s.is_active,

        'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S') if s.created_at else None

    } for s in rows])

@router.post("/scripts", response_model=Response)

def create_script(req: ScriptCreate, db: Session = Depends(get_db)):

    s = Script(

        name=req.name, script_type=req.script_type,

        description=req.description, content=req.content

    )

    db.add(s)

    db.commit()

    db.refresh(s)

    return Response(msg='脚本创建成功', data={'id': s.id, 'name': s.name})

@router.put("/scripts/{script_id}", response_model=Response)

def update_script(script_id: int, req: ScriptUpdate, db: Session = Depends(get_db)):

    s = db.query(Script).filter(Script.id == script_id).first()

    if not s:

        return Response(code=404, msg='脚本不存在')

    for field in ['name', 'script_type', 'description', 'content', 'is_active']:

        val = getattr(req, field, None)

        if val is not None:

            setattr(s, field, val)

    db.commit()

    return Response(msg='脚本更新成功')

@router.delete("/scripts/{script_id}", response_model=Response)

def delete_script(script_id: int, db: Session = Depends(get_db)):

    s = db.query(Script).filter(Script.id == script_id).first()

    if not s:

        return Response(code=404, msg='脚本不存在')

    db.delete(s)

    db.commit()

    return Response(msg='脚本删除成功')

@router.post("/scripts/execute", response_model=Response)

def execute_scripts(req: ScriptExecRequest, db: Session = Depends(get_db)):

    scripts = db.query(Script).filter(

        Script.id.in_(req.script_ids), Script.is_active == True

    ).all()

    results = []

    for s in scripts:

        err = _check_script_safety(s.content)

        if err:

            results.append({'id': s.id, 'name': s.name, 'exit_code': 1, 'stdout': '', 'stderr': err})

        else:

            r = _run_script(s.content, s.script_type, env=req.extra_env or None)

            results.append({'id': s.id, 'name': s.name, **r})

    return Response(data={'results': results, 'total': len(results)})

@router.post("/block", response_model=Response)

def execute_block(req: BlockExecRequest, db: Session = Depends(get_db)):

    script = db.query(Script).filter(

        Script.id == req.script_id, Script.is_active == True

    ).first()

    if not script:

        return Response(code=404, msg='封堵脚本不存在或已停用')

    results = []

    for t in req.targets:

        r = _run_script(script.content, script.script_type, env=t.env or None)

        results.append({'ip': t.ip, 'name': script.name, **r})

    return Response(data={'results': results, 'total': len(results)})

@router.post("/execute", response_model=Response)

def execute_adhoc(req: AdhocExecRequest):

    err = _check_script_safety(req.script)

    if err:

        return Response(code=400, msg=err)

    result = _run_script(req.script, req.type)

    return Response(data=result)

# ?? Traffic Inspection ????????????????????????????????????????????????????????

@router.post("/traffic", response_model=Response)

def inspect_traffic(req: TrafficQuery, db: Session = Depends(get_db)):

    es = _get_es_service(db)

    index = req.index or es.config.default_index

    now = datetime.utcnow()

    gte = (now - timedelta(minutes=req.window_minutes)).isoformat() + 'Z'

    field_types = es.get_index_fields(index) if es.client else {}

    must_clauses = [{"range": {"@timestamp": {"gte": gte}}}]

    if req.filters:

        for filt in req.filters:

            field = filt.get('field', '')

            op = filt.get('operator', 'equals')

            val = filt.get('value', '')

            if not field:

                continue

            ft = field_types.get(field)

            if ft == 'text' and field_types.get(f'{field}.keyword'):

                field = f'{field}.keyword'

            if op == 'equals':

                must_clauses.append({'term': {field: val}})

            elif op == 'contains':

                must_clauses.append({'wildcard': {field: f'*{val}*'}})

            elif op == 'gt':

                must_clauses.append({'range': {field: {'gt': val}}})

            elif op == 'lt':

                must_clauses.append({'range': {field: {'lt': val}}})

            elif op == 'gte':

                must_clauses.append({'range': {field: {'gte': val}}})

            elif op == 'lte':

                must_clauses.append({'range': {field: {'lte': val}}})

    group_field = req.group_by_field

    if field_types.get(group_field) == 'text' and field_types.get(f"{group_field}.keyword"):

        group_field = f"{group_field}.keyword"

    body = {

        "size": 0,

        "query": {"bool": {"must": must_clauses}},

        "aggs": {

            "by_field": {

                "terms": {"field": group_field, "size": 100},

                "aggs": {"unique_docs": {"cardinality": {"field": "request_uri.keyword"}}}

            }

        }

    }

    try:

        res = es.client.search(index=index, body=body)

        buckets = res.get('aggregations', {}).get('by_field', {}).get('buckets', [])

        total = sum(b.get('doc_count', 0) for b in buckets)

        domains = [

            {'key': b['key'], 'count': b['doc_count'], 'unique_uris': b.get('unique_docs', {}).get('value', 0)}

            for b in buckets

        ]

        return Response(data={

            'domains': domains, 'total': total,

            'window_minutes': req.window_minutes,

            'group_by_field': req.group_by_field,

            'index': index

        })

    except Exception as e:

        return Response(code=500, msg=f'ES查?失败: {str(e)}')

# ?? Prometheus Direct Metrics ??????????????????????????????????????????????????

@router.get("/prometheus-metrics", response_model=Response)

def prometheus_metrics(db: Session = Depends(get_db)):

    url_row = db.query(SystemConfig).filter(SystemConfig.key == 'prometheus_url').first()

    user_row = db.query(SystemConfig).filter(SystemConfig.key == 'prometheus_user').first()

    pwd_row = db.query(SystemConfig).filter(SystemConfig.key == 'prometheus_password').first()

    prom_url = url_row.value if url_row else 'http://localhost:9090'

    prom_user = user_row.value if user_row else ''

    prom_pwd = pwd_row.value if pwd_row else ''

    def _query(q: str) -> Optional[float]:

        try:

            req = urllib.request.Request(

                f'{prom_url}/api/v1/query',

                data=urllib.parse.urlencode({'query': q}).encode(),

                headers={'Content-Type': 'application/x-www-form-urlencoded'}

            )

            if prom_user:

                import base64

                req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{prom_user}:{prom_pwd}'.encode()).decode())

            with urllib.request.urlopen(req, timeout=5) as resp:

                result = json.loads(resp.read())

                vals = result.get('data', {}).get('result', [])

                if vals:

                    return float(vals[0]['value'][1])

        except Exception:

            pass

        return None

    try:

        cpu = _query('rate(node_cpu_seconds_total{mode!="idle"}[5m]) * 100 / on(instance) group_left() count(node_cpu_seconds_total) by (instance)')

        mem_used = _query('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')

        mem_total = _query('node_memory_MemTotal_bytes')

        disk_used = _query('node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}')

        disk_total = _query('node_filesystem_size_bytes{mountpoint="/"}')

        return Response(data={

            'connected': True,

            'cpu': {'avg': round(cpu, 2) if cpu else None, 'peak': round(cpu * 1.2, 2) if cpu else None},

            'memory': {

                'avg': round((1 - (mem_total - mem_used or 0) / (mem_total or 1)) * 100, 2),

                'peak': round((1 - (mem_total - mem_used or 0) / (mem_total or 1)) * 100, 2)

            } if mem_total else None,

            'disk': {

                'avg': round((disk_used / disk_total * 100) if disk_total else 0, 2),

                'peak': round((disk_used / disk_total * 100) if disk_total else 0, 2)

            } if disk_total else None

        })

    except Exception as e:

        return Response(data={'connected': False, 'error': str(e)})

# ?? Grafana / Prometheus Metrics ?????????????????????????????????????????????

def _compute_server_metrics(db: Session, end_ts: int, seconds: int):

    """

    计算每台服务器在 [end_ts - seconds, end_ts] 窗口内的 CPU/内存/磁盘 平均与峰值??    返回 (servers: list, prom_url: str, error: str|None)

    servers 元素：{instance, alias, cpu:{avg,peak}, memory:{avg,peak}, disks:[{mountpoint,avg,peak}]}

    """

    import ssl

    grafana_url = _cfg_get(db, 'grafana_url', 'http://localhost:3000').rstrip('/')

    if not grafana_url:

        return [], '', 'grafana_url 未配置'

    headers = _grafana_headers(db)

    headers['Content-Type'] = 'application/json'

    ctx = ssl.create_default_context()

    ctx.check_hostname = False

    ctx.verify_mode = ssl.CERT_NONE

    prom_url = None

    prom_uid = None

    try:

        req = urllib.request.Request(f'{grafana_url}/api/datasources', headers=headers)

        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:

            for ds in json.loads(resp.read()):

                if ds.get('type') == 'prometheus':

                    prom_url = ds.get('url', '').rstrip('/')

                    prom_uid = str(ds.get('uid', ''))

                    break

    except Exception:

        pass

    if not prom_url:

        return [], '', '无法从 Grafana 获取 Prometheus 数据'

    _step = 60 if seconds <= 7200 else (300 if seconds <= 86400 else 900)

    start = end_ts - seconds

    def _query_range(expr: str):

        try:

            proxy_url = f'{grafana_url}/api/datasources/proxy/uid/{prom_uid}'

            params = urllib.parse.urlencode({'query': expr, 'start': start, 'end': end_ts, 'step': _step})

            req = urllib.request.Request(f'{proxy_url}/api/v1/query_range?{params}', headers=headers)

            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:

                result = json.loads(resp.read())

            out = {}

            for item in result.get('data', {}).get('result', []):

                inst = item.get('metric', {}).get('instance', 'unknown')

                if inst not in out:

                    out[inst] = []

                for ts_str, val_str in item.get('values', []):

                    out[inst].append({'timestamp': int(float(ts_str)), 'value': float(val_str)})

            return out

        except Exception:

            return {}

    def _stats(series):

        if not series:

            return None, None

        vals = [item['value'] for item in series]

        return round(sum(vals) / len(vals), 2), round(max(vals), 2)

    cpu_expr = 'rate(node_cpu_seconds_total{mode!="idle"}[5m]) * 100'

    mem_expr = '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100'

    disk_root_expr = '(node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}) / node_filesystem_size_bytes{mountpoint="/"} * 100'

    disk_logs_expr = '(node_filesystem_size_bytes{mountpoint="/data/logs"} - node_filesystem_free_bytes{mountpoint="/data/logs"}) / node_filesystem_size_bytes{mountpoint="/data/logs"} * 100'

    # Parallel: fire all 4 PromQL queries simultaneously

    cpu_series = {}

    mem_series = {}

    disk_root_series = {}

    disk_logs_series = {}

    with ThreadPoolExecutor(max_workers=4) as pool:

        futures = {

            pool.submit(_query_range, cpu_expr): "cpu",

            pool.submit(_query_range, mem_expr): "mem",

            pool.submit(_query_range, disk_root_expr): "disk_root",

            pool.submit(_query_range, disk_logs_expr): "disk_logs",

        }

        for fut in as_completed(futures):

            key = futures[fut]

            try:

                result = fut.result()

            except Exception as exc:

                result = {}

                print(f"_query_range {key} failed:", exc)

            if key == "cpu":

                cpu_series = result

            elif key == "mem":

                mem_series = result

            elif key == "disk_root":

                disk_root_series = result

            elif key == "disk_logs":

                disk_logs_series = result

    try:

        aliases = json.loads(_cfg_get(db, 'server_aliases', '{}'))

    except Exception:

        aliases = {}

    all_instances = set(cpu_series) | set(mem_series) | set(disk_root_series) | set(disk_logs_series)

    servers = []

    for inst in sorted(all_instances):

        cpu_avg, cpu_peak = _stats(cpu_series.get(inst, []))

        mem_avg, mem_peak = _stats(mem_series.get(inst, []))

        dr_vals = disk_root_series.get(inst, [])

        dr_avg, dr_peak = _stats(dr_vals)

        dl_vals = disk_logs_series.get(inst, [])

        dl_avg, dl_peak = _stats(dl_vals)

        disks = []

        if dr_vals:

            disks.append({'mountpoint': '/', 'avg': dr_avg, 'peak': dr_peak})

        if dl_vals:

            disks.append({'mountpoint': '/data/logs', 'avg': dl_avg, 'peak': dl_peak})

        # 合并?有挂载点的??series（供前?趋势图使?

        disk_series = []

        if dr_vals:

            disk_series.extend(dr_vals)

        if dl_vals:

            disk_series.extend(dl_vals)

        seen_ts = set()

        disk_series_dedup = []

        for p in sorted(disk_series, key=lambda x: x['timestamp']):

            if p['timestamp'] not in seen_ts:

                seen_ts.add(p['timestamp'])

                disk_series_dedup.append(p)

        servers.append({

            'instance': inst,

            'alias': aliases.get(inst, ''),

            'cpu': {'avg': cpu_avg, 'peak': cpu_peak},

            'memory': {'avg': mem_avg, 'peak': mem_peak},

            'disks': disks,

            'cpu_series': cpu_series.get(inst, []),

            'memory_series': mem_series.get(inst, []),

            'disk_series': disk_series_dedup

        })

    return servers, prom_url, None

@router.get("/grafana-metrics", response_model=Response)

def grafana_metrics(time_range: str = Query(default="1h"), db: Session = Depends(get_db)):

    """

    Grafana 系统指标：从 Grafana 数据源配??Prometheus URL

    使用 Prometheus /api/v1/query_range 拉取历史数据

    计算每台服务?CPU/内存/磁盘 的平均和峰??    time_range: 1h | 6h | today | 1d | 7d（默?1h?    """

    import ssl

    import time as _time

    grafana_url = _cfg_get(db, 'grafana_url', 'http://localhost:3000').rstrip('/')

    if not grafana_url:

        return Response(data={'connected': False, 'error': 'grafana_url 未配置'})

    headers = _grafana_headers(db)

    headers['Content-Type'] = 'application/json'

    ctx = ssl.create_default_context()

    ctx.check_hostname = False

    ctx.verify_mode = ssl.CERT_NONE

    # Step 1: 获取 Prometheus 数据源的 URL + UID

    prom_url = None

    prom_uid = None

    try:

        req = urllib.request.Request(f'{grafana_url}/api/datasources', headers=headers)

        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:

            for ds in json.loads(resp.read()):

                if ds.get('type') == 'prometheus':

                    prom_url = ds.get('url', '').rstrip('/')

                    prom_uid = str(ds.get('uid', ''))

                    break

    except Exception:

        pass

    if not prom_url:

        return Response(data={

            'connected': False,

                'error': '无法从 Grafana 获取 Prometheus 数据，请检查 Grafana 数据源配置'

        })

    # 解析时间范围

    _range_map = {'1h': 3600, '6h': 21600, 'today': 86400, '1d': 86400, '7d': 604800}

    _seconds = _range_map.get(time_range, 3600)

    _time_label_map = {
        '1h': '最近 1 小时', '6h': '最近 6 小时', 'today': '今日',
        '1d': '最近 1 天', '7d': '最近 7 天',
    }
    _time_label = _time_label_map.get(time_range, '最近 1 小时')

    _time_label = _time_label_map.get(time_range, '??1 小时')

    # 复用统一计算函数

    now = int(time.time())

    servers, prom_url, _err = _compute_server_metrics(db, now, _seconds)

    if not servers:

        return Response(data={

            'connected': _err is None,

            'source': 'grafana',

            'prom_url': prom_url,

            'time_range': _time_label,

            'servers': [],

            'custom': [],

            'error': _err or '?询到任何服务器指标，请确?Prometheus 已采?node_exporter 数据'

        })

    # Step 3: ?义指标（即时 + 趋势?    def _query_range(expr):

        try:

            proxy_url = f'{grafana_url}/api/datasources/proxy/uid/{prom_uid}'

            params = urllib.parse.urlencode({'query': expr, 'start': now - _seconds, 'end': now, 'step': _step})

            req = urllib.request.Request(f'{proxy_url}/api/v1/query_range?{params}', headers=headers)

            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:

                result = json.loads(resp.read())

            out = {}

            for item in result.get('data', {}).get('result', []):

                inst = item.get('metric', {}).get('instance', 'unknown')

                if inst not in out:

                    out[inst] = []

                for ts_str, val_str in item.get('values', []):

                    out[inst].append({'timestamp': int(float(ts_str)), 'value': float(val_str)})

            return out

        except Exception:

            return {}

    def _query_instant(expr):

        try:

            proxy_url = f'{grafana_url}/api/datasources/proxy/uid/{prom_uid}'

            params = urllib.parse.urlencode({'query': expr})

            req = urllib.request.Request(f'{proxy_url}/api/v1/query?{params}', headers=headers)

            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:

                result = json.loads(resp.read())

            out = {}

            for item in result.get('data', {}).get('result', []):

                inst = item.get('metric', {}).get('instance', 'unknown')

                out[inst] = float(item.get('value', ['', 0])[1])

            return out

        except Exception:

            return {}

    custom_metrics = db.query(CustomMetric).all()

    custom_results = []

    # Parallel: batch all custom metric queries

    if custom_metrics:

        # Phase 1: all _query_instant in parallel

        instant_map = {}

        with ThreadPoolExecutor(max_workers=8) as pool:

            instant_futs = {pool.submit(_query_instant, m.promql): m for m in custom_metrics}

            for fut in as_completed(instant_futs):

                m = instant_futs[fut]

                try:

                    instant_map[m.id] = fut.result()

                except Exception:

                    instant_map[m.id] = {}

        # Phase 2: all _query_range in parallel

        with ThreadPoolExecutor(max_workers=8) as pool:

            range_futs = {pool.submit(_query_range, m.promql): m for m in custom_metrics}

            for fut in as_completed(range_futs):

                m = range_futs[fut]

                try:

                    inst_series_map = fut.result()

                except Exception:

                    inst_series_map = {}

                series_data = []

                for inst_, pts in inst_series_map.items():

                    series_data.extend(pts)

                seen_ts = set()

                series_data_dedup = []

                for p in sorted(series_data, key=lambda x: x["timestamp"]):

                    if p["timestamp"] not in seen_ts:

                        seen_ts.add(p["timestamp"])

                        series_data_dedup.append(p)

                custom_results.append({

                    'id': m.id, 'name': m.name, 'description': m.description,

                    'promql': m.promql, 'unit': m.unit,

                    'values': [{'instance': inst, 'value': round(v, 4)} for inst, v in instant_map.get(m.id, {}).items()],

                    'series_data': series_data_dedup

                })
    return Response(data={

        'connected': True,

        'source': 'grafana',

        'prom_url': prom_url,

        'time_range': _time_label,

        'servers': servers,

        'custom': custom_results

    })

# ?? VirusTotal Country Lookup ?????????????????????????????????????????????????

@router.post("/lookup-country", response_model=Response)

def lookup_country(req: List[str], db: Session = Depends(get_db)):

    """Lookup country for multiple IPs via ipinfo.io (primary) + VirusTotal (fallback)."""

    results = {}

    for ip in req:

        country_code = _get_ipinfo_country(ip)

        if country_code:

            results[ip] = _to_chinese_country(country_code)

            continue

        raw = _get_virustotal_info(ip, db)

        if raw:

            results[ip] = _to_chinese_country(raw.get('country', ''))

        else:

            results[ip] = ''

    return Response(data=results)

# ?? Python 依赖管理 ????????????????????????????????????????????????????????????

@router.get("/pip-packages", response_model=Response[List[dict]])

def list_pip_packages():

    """列出已安装的 Python 包（pip list?"""

    try:

        result = subprocess.run(

            ['pip', 'list', '--format=json'],

            capture_output=True, timeout=30

        )

        packages = json.loads(result.stdout)

        return Response(data=[{'name': p['name'], 'version': p['version']} for p in packages])

    except Exception as e:

        return Response(code=400, msg=f"获取包列表失? {str(e)}", data=[])

@router.post("/pip-install", response_model=Response)

def pip_install(req: PipInstallReq, current_user: User = Depends(get_current_user)):

    """安? Python ?"""

    pkg = req.package.strip()

    if not pkg:

        return Response(code=400, msg="包名不能为空")

    if not re.match(r'^[a-zA-Z0-9._=\-^~\[\] ]+$', pkg):

        return Response(code=400, msg="包名格式不合规，?许字母?数字??-_=^~[]")

    try:

        result = subprocess.run(

            ['pip', 'install', pkg, '--quiet', '--no-input'],

            capture_output=True, timeout=120

        )

        stdout = result.stdout.decode('utf-8', errors='replace')

        stderr = result.stderr.decode('utf-8', errors='replace')

        if result.returncode == 0:

            return Response(msg=f"安?成功: {pkg}", data={'package': pkg, 'ok': True})

        else:

            err_msg = stderr or stdout

            err_msg = re.sub(r'\x1b\[[0-9;]*m', '', err_msg).strip()

            return Response(code=400, msg=f"安?失败: {err_msg[:500]}")

    except subprocess.TimeoutExpired:

        return Response(code=400, msg="安?超时（超?分钟?")

    except Exception as e:

        return Response(code=400, msg=f"安?异常: {str(e)}")

@router.post("/pip-uninstall", response_model=Response)

def pip_uninstall(req: PipUninstallReq, current_user: User = Depends(get_current_user)):

    """卸载 Python 包（仅?理员?"""

    if current_user.role != 'admin':

        return Response(code=403, msg="仅?理员?载包")

    pkg = req.package.strip()

    if not pkg:

        return Response(code=400, msg="包名不能为空")

    if not re.match(r'^[a-zA-Z0-9._=\-^~]+$', pkg):

        return Response(code=400, msg="包名格式不合")

    CORE_PACKAGES = {'pip', 'setuptools', 'wheel', 'fastapi', 'uvicorn', 'sqlalchemy',

                     'pydantic', 'python-multipart', 'cryptography', 'python-jose', 'passlib'}

    if pkg.lower() in CORE_PACKAGES:

        return Response(code=400, msg=f"禁?卸载核心依赖: {pkg}")

    try:

        result = subprocess.run(

            ['pip', 'uninstall', pkg, '-y', '--quiet'],

            capture_output=True, timeout=60

        )

        if result.returncode == 0:

            return Response(msg=f"卸载成功: {pkg}")

        else:

            err = re.sub(r'\x1b\[[0-9;]*m', '', result.stderr.decode('utf-8', errors='replace')).strip()

            return Response(code=400, msg=f"卸载失败: {err[:300]}")

    except Exception as e:

        return Response(code=400, msg=f"卸载异常: {str(e)}")

# ?? Custom Metrics CRUD ???????????????????????????????????????????????????????

@router.get("/custom-metrics", response_model=Response)

def list_custom_metrics(db: Session = Depends(get_db)):

    """列出?有自定义指标"""

    metrics = db.query(CustomMetric).order_by(CustomMetric.created_at.desc()).all()

    return Response(data=[{

        'id': m.id,

        'name': m.name,

        'description': m.description,

        'promql': m.promql,

        'unit': m.unit,

        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else '',

        'updated_at': m.updated_at.strftime('%Y-%m-%d %H:%M:%S') if m.updated_at else ''

    } for m in metrics])

@router.post("/custom-metrics", response_model=Response)

def create_custom_metric(req: CustomMetricCreate, db: Session = Depends(get_db),

                          current_user: User = Depends(get_current_user)):

    """创建?义指标（admin only?"""

    if current_user.role != 'admin':

        return Response(code=403, msg="仅?理员??理自定义指标")

    if db.query(CustomMetric).filter(CustomMetric.name == req.name).first():

        return Response(code=409, msg=f"指标名称「{req.name}」已存在")

    metric = CustomMetric(

        name=req.name,

        description=req.description,

        promql=req.promql,

        unit=req.unit

    )

    db.add(metric)

    db.commit()

    return Response(msg=f"?义指标?{req.name}」创建成")

@router.put("/custom-metrics/{metric_id}", response_model=Response)

def update_custom_metric(metric_id: int, req: CustomMetricUpdate, db: Session = Depends(get_db),

                          current_user: User = Depends(get_current_user)):

    """更新?义指标（admin only?"""

    if current_user.role != 'admin':

        return Response(code=403, msg="仅?理员??理自定义指标")

    metric = db.query(CustomMetric).filter(CustomMetric.id == metric_id).first()

    if not metric:

        return Response(code=404, msg="指标不存")

    if req.name is not None and req.name != metric.name:

        if db.query(CustomMetric).filter(CustomMetric.name == req.name, CustomMetric.id != metric_id).first():

            return Response(code=409, msg=f"指标名称「{req.name}」已存在")

        metric.name = req.name

    if req.description is not None:

        metric.description = req.description

    if req.promql is not None:

        metric.promql = req.promql

    if req.unit is not None:

        metric.unit = req.unit

    db.commit()

    return Response(msg="?义指标更新成")

@router.delete("/custom-metrics/{metric_id}", response_model=Response)

def delete_custom_metric(metric_id: int, db: Session = Depends(get_db),

                          current_user: User = Depends(get_current_user)):

    """删除?义指标（admin only?"""

    if current_user.role != 'admin':

        return Response(code=403, msg="仅?理员??理自定义指标")

    metric = db.query(CustomMetric).filter(CustomMetric.id == metric_id).first()

    if not metric:

        return Response(code=404, msg="指标不存")

    db.delete(metric)

    db.commit()

    return Response(msg=f"?义指标?{metric.name}」已删除")

@router.get("/server-aliases", response_model=Response)
def get_server_aliases(db: Session = Depends(get_db)):
    """获取服务器别名映射"""
    row = db.query(SystemConfig).filter(SystemConfig.key == 'server_aliases').first()
    if not row or not row.value:
        return Response(data={})
    try:
        return Response(data=json.loads(row.value))
    except Exception:
        return Response(data={})


@router.put("/server-aliases", response_model=Response)
def set_server_aliases(req: Dict[str, str], db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """更新服务器别名映射（整体覆盖）"""
    if current_user.role != 'admin':
        return Response(code=403, msg="仅管理员可管理服务器别名")
    row = db.query(SystemConfig).filter(SystemConfig.key == 'server_aliases').first()
    if not row:
        row = SystemConfig(key='server_aliases', value='{}')
        db.add(row)
    row.value = json.dumps(req, ensure_ascii=False)
    db.commit()
    return Response(msg="别名保存成功", data=req)

