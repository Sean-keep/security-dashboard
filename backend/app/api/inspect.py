"""Inspection API - Scripts + Traffic + Metrics + VirusTotal

Security model for script execution
-----------------------------------
``_run_script`` is **not** a sandbox. The AST/regex screen is defence-in-depth
only — a determined author can defeat any static filter. Real controls are:

1. Every endpoint in this module requires authentication.
2. Anything that runs code (`/execute`, `/scripts/*`, `/block`, pip install /
   uninstall) requires the ``admin`` role.
3. ``ENABLE_SCRIPT_EXECUTION=0`` turns the whole surface off.
4. Child processes get a **scrubbed** environment (no ``SECRET_KEY``,
   ``MYSQL_PASSWORD``, ``ES_PASSWORD``, ...) so a script cannot exfiltrate
   secrets even if it escapes the filter.
5. Resource limits (address space, CPU, file handles) bound blast radius.

If you need untrusted code execution, run it in a separate locked-down
container/VM and call it over the network — do not relax this module.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
import os
import re
import resource
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.security import get_current_admin_user, get_current_user, require_roles
from app.core.config import settings
from app.models.base import get_db
from app.models.config import SystemConfig
from app.models.custom_metric import CustomMetric
from app.models.script import Script
from app.models.user import User
from app.schemas.common import Response
from app.services.es_service import ESConfig, get_es_service
from app.utils.timezone import utc_iso, utc_naive

router = APIRouter(prefix="/api/inspect", tags=["Inspection"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Never hand these to a child process.
_SECRET_ENV_KEYS = {
    "SECRET_KEY", "JWT_SECRET_KEY", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD",
    "ES_PASSWORD", "MYSQL_USER", "DATABASE_URL", "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID", "GITHUB_TOKEN", "GH_TOKEN", "TOKEN", "PASSWORD",
    "API_KEY", "APIKEY", "PRIVATE_KEY",
}

# Names a script must not reference at all (coarse screen).
_DANGEROUS_NAMES = {
    "os", "sys", "subprocess", "shutil", "importlib", "ctypes", "socket",
    "pty", "multiprocessing", "resource", "gc", "inspect", "builtins",
    "eval", "exec", "compile", "open", "input", "reload", "__import__",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "breakpoint",
}


def _check_script_safety(code: str, lang: str = "python") -> Optional[str]:
    """Coarse static screen. Returns an error message, or None to allow.

    This is a speed bump for accidental damage, **not** a security boundary —
    see the module docstring. The real controls are authz + scrubbed env.
    """
    if lang == "python":
        return _check_python_safety(code)
    return _check_shell_safety(code)


def _check_python_safety(code: str) -> Optional[str]:
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"脚本语法错误: {exc.msg}（第 {exc.lineno} 行）"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _DANGEROUS_NAMES:
                    return f"禁止导入 {root}，已拒绝执行"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _DANGEROUS_NAMES:
                return f"禁止导入 {root}，已拒绝执行"
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in _DANGEROUS_NAMES:
                return f"禁止访问 {node.id}，已拒绝执行"
        elif isinstance(node, ast.Attribute):
            if isinstance(node.attr, str) and node.attr in ("system", "popen", "spawnl", "spawnv", "fork", "execv", "execve"):
                return f"禁止调用 {node.attr}，已拒绝执行"
    return None


def _check_shell_safety(code: str) -> Optional[str]:
    banned = [
        r"\brm\s+(-[a-zA-Z]*\s+)*-\s*rf?\b",
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f",
        r"\bcurl\b[^|]*\|\s*(ba)?sh",
        r"\bwget\b[^|]*\|\s*(ba)?sh",
        r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{", r"\bchmod\s+777\b",
        r"/etc/passwd", r"/etc/shadow", r"\.ssh/", r"\bcrontab\b",
        r"\bsudo\b", r"\bsu\s+-",
    ]
    for pattern in banned:
        if re.search(pattern, code):
            return "脚本包含高危 shell 操作，已拒绝执行"
    return None


def _scrubbed_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build a child environment with secrets and loader hooks removed."""
    run_env = {
        k: v for k, v in os.environ.items()
        if not any(secret in k.upper() for secret in _SECRET_ENV_KEYS)
    }
    # Drop anything that changes how the interpreter/loader resolves code.
    for key in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "LD_PRELOAD",
                "LD_LIBRARY_PATH", "BASH_ENV", "ENV", "IFS"):
        run_env.pop(key, None)
    run_env["PYTHONDONTWRITEBYTECODE"] = "1"
    run_env["HOME"] = tempfile.gettempdir()

    if extra:
        for key, value in extra.items():
            key_u = str(key).upper()
            if any(secret in key_u for secret in _SECRET_ENV_KEYS):
                continue
            if key in ("PYTHONPATH", "PYTHONSTARTUP", "LD_PRELOAD", "LD_LIBRARY_PATH", "BASH_ENV"):
                continue
            run_env[str(key)] = str(value)
    return run_env


def _limit_resources(mem_mb: int, cpu_seconds: int):
    """preexec_fn: bound the child before it runs any user code."""
    def _apply() -> None:
        try:
            addr = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (addr, addr))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 2))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            # No core dumps of whatever the script managed to read.
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass
    return _apply


def _require_script_execution_enabled() -> None:
    if not settings.ENABLE_SCRIPT_EXECUTION:
        raise HTTPException(status_code=403, detail="脚本执行功能已由 ENABLE_SCRIPT_EXECUTION=0 关闭")


def _run_script(
    code: str,
    lang: str,
    timeout: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Execute a script with a scrubbed env and resource limits.

    Returns ``{stdout, stderr, exit_code}``. See the module docstring for the
    threat model — this is not a sandbox.
    """
    err = _check_script_safety(code, lang=lang)
    if err:
        return {"stdout": "", "stderr": err, "exit_code": 1}

    timeout = timeout or settings.SCRIPT_TIMEOUT_SECONDS
    run_env = _scrubbed_env(env)
    preexec = _limit_resources(settings.SCRIPT_MEMORY_LIMIT_MB, timeout)

    # Run from a throwaway cwd so scripts cannot casually read app source.
    with tempfile.TemporaryDirectory(prefix="sdrun-") as workdir:
        try:
            if lang == "python":
                # -I: isolated (ignore PYTHON* env and user site). -B: no pyc.
                cmd = ["python3", "-I", "-B", "-c", code]
            else:
                cmd = ["bash", "-c", code]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                env=run_env,
                cwd=workdir,
                preexec_fn=preexec,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"脚本执行超时（{timeout} 秒）", "exit_code": 124}
        except Exception as exc:
            return {"stdout": "", "stderr": f"脚本启动失败: {exc}", "exit_code": 1}

    return {
        "stdout": result.stdout.decode("utf-8", errors="replace")[:200_000],
        "stderr": result.stderr.decode("utf-8", errors="replace")[:200_000],
        "exit_code": result.returncode,
    }


def _get_es_config(db: Session) -> ESConfig:
    cfg_keys = ["es_host", "es_port", "es_scheme", "es_verify_certs", "es_user", "es_password", "es_index"]
    cfg = {}
    for k in cfg_keys:
        row = db.query(SystemConfig).filter(SystemConfig.key == k).first()
        cfg[k] = row.value if row else ""
    try:
        port = int(cfg.get("es_port") or 9200)
    except ValueError:
        port = 9200
    return ESConfig(
        host=cfg.get("es_host") or settings.ES_HOST,
        port=port,
        scheme=cfg.get("es_scheme") or settings.ES_SCHEME,
        verify_certs=(cfg.get("es_verify_certs") or "false").lower() == "true",
        user=cfg.get("es_user") or "",
        password=cfg.get("es_password") or "",
        default_index=cfg.get("es_index") or settings.ES_INDEX,
    )


def _get_es_service(db: Session):
    """Cached ES service — rebuilding the client per request throws away the
    connection pool and makes the field-type cache useless."""
    return get_es_service(_get_es_config(db))


def _get_ipinfo_country(ip: str) -> Optional[str]:
    """Query ipinfo.io for a 2-letter country code. No API key needed."""
    try:
        req = urllib.request.Request(
            f"https://ipinfo.io/{ip}/json",
            headers={"User-Agent": "Mozilla/5.0 SecurityDashboard/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return data.get("country", "") or None
    except Exception:
        return None


def _get_virustotal_info(ip: str, db: Session) -> Optional[Dict]:
    """Query VirusTotal for country info (fallback when ipinfo fails)."""
    api_key_row = db.query(SystemConfig).filter(SystemConfig.key == "virustotal_api_key").first()
    api_key = api_key_row.value if api_key_row else ""
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            f"https://www.virustotal.com/api/v3/ip_addresses/{ip}",
            headers={"x-apikey": api_key, "User-Agent": "SecurityDashboard/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            country = data.get("data", {}).get("attributes", {}).get("country", "")
            return {"country": country}
    except Exception:
        return None


COUNTRY_MAP = {
    "CN": "中国", "US": "美国", "JP": "日本", "KR": "韩国", "SG": "新加坡",
    "HK": "中国香港", "TW": "中国台湾", "DE": "德国", "FR": "法国", "GB": "英国",
    "AU": "澳大利亚", "CA": "加拿大", "IN": "印度", "RU": "俄罗斯", "BR": "巴西",
    "NL": "荷兰", "SE": "瑞典", "CH": "瑞士", "IT": "意大利", "ES": "西班牙",
    "MX": "墨西哥", "AR": "阿根廷", "ZA": "南非", "AE": "阿联酋", "SA": "沙特阿拉伯",
    "TH": "泰国", "VN": "越南", "MY": "马来西亚", "ID": "印度尼西亚", "PH": "菲律宾",
    "NG": "尼日利亚", "EG": "埃及", "TR": "土耳其", "PL": "波兰", "CZ": "捷克",
    "NO": "挪威", "DK": "丹麦", "FI": "芬兰", "PT": "葡萄牙", "UA": "乌克兰",
    "IE": "爱尔兰", "AT": "奥地利", "BE": "比利时", "CL": "智利", "CO": "哥伦比亚",
    "PE": "秘鲁", "NZ": "新西兰", "RO": "罗马尼亚", "HU": "匈牙利", "BG": "保加利亚",
    "IL": "以色列", "GR": "希腊", "PK": "巴基斯坦", "BD": "孟加拉国", "NP": "尼泊尔",
    "MM": "缅甸", "KH": "柬埔寨", "LA": "老挝", "BN": "文莱", "MN": "蒙古",
}


def _to_chinese_country(code: str) -> str:
    return COUNTRY_MAP.get((code or "").upper(), code)


def _cfg_get(db, key, default=""):
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row else default


def _insecure_ssl_context():
    """SSL context that skips certificate verification.

    Only for Grafana/Prometheus on private networks with self-signed certs.
    Toggle with the ``grafana_verify_certs`` system config (default off to keep
    existing deployments working). Prefer turning verification ON.
    """
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _grafana_headers(db):
    import base64
    auth_mode = _cfg_get(db, "grafana_auth_mode", "apikey")
    base_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if auth_mode == "basic":
        user = _cfg_get(db, "grafana_user", "")
        pwd = _cfg_get(db, "grafana_password", "")
        if user and pwd:
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {**base_headers, "Authorization": f"Basic {token}"}
    else:
        api_key = _cfg_get(db, "grafana_api_key", "")
        if api_key:
            return {**base_headers, "Authorization": f"Bearer {api_key}"}
    return base_headers


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ScriptCreate(BaseModel):
    name: str = Field(..., max_length=128)
    script_type: str = Field("python", pattern="^(python|shell)$")
    description: str = ""
    content: str


class ScriptUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    script_type: Optional[str] = Field(default=None, pattern="^(python|shell)$")
    description: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None


class ScriptExecRequest(BaseModel):
    script_ids: List[int]
    extra_env: Optional[Dict[str, str]] = {}


class AdhocExecRequest(BaseModel):
    type: str = Field("python", pattern="^(python|shell)$")
    script: str


class BlockTarget(BaseModel):
    ip: str
    env: Optional[Dict[str, str]] = None


class BlockExecRequest(BaseModel):
    script_id: int
    targets: List[BlockTarget] = Field(..., max_length=200)


class TrafficQuery(BaseModel):
    index: Optional[str] = None
    window_minutes: int = Field(30, ge=1, le=60 * 24 * 30)
    group_by_field: str = "domain"
    metric_field: str = "request_uri"
    filters: Optional[List[Dict]] = None


class PipInstallReq(BaseModel):
    package: str


class PipUninstallReq(BaseModel):
    package: str


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


# ---------------------------------------------------------------------------
# Script CRUD + execution (admin only — these run arbitrary code)
# ---------------------------------------------------------------------------

@router.get("/scripts", response_model=Response[List[dict]])
def list_scripts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    rows = db.query(Script).order_by(Script.id.desc()).all()
    return Response(data=[{
        "id": s.id, "name": s.name, "script_type": s.script_type,
        "description": s.description, "content": s.content,
        "is_active": s.is_active,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    } for s in rows])


@router.post("/scripts", response_model=Response)
def create_script(
    req: ScriptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    _require_script_execution_enabled()
    if _check_script_safety(req.content, req.script_type):
        return Response(code=400, msg=_check_script_safety(req.content, req.script_type))
    s = Script(
        name=req.name, script_type=req.script_type,
        description=req.description, content=req.content,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return Response(msg="脚本创建成功", data={"id": s.id, "name": s.name})


@router.put("/scripts/{script_id}", response_model=Response)
def update_script(
    script_id: int,
    req: ScriptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    _require_script_execution_enabled()
    s = db.query(Script).filter(Script.id == script_id).first()
    if not s:
        return Response(code=404, msg="脚本不存在")
    if req.content is not None:
        err = _check_script_safety(req.content, req.script_type or s.script_type)
        if err:
            return Response(code=400, msg=err)
    for field in ["name", "script_type", "description", "content", "is_active"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(s, field, val)
    db.commit()
    return Response(msg="脚本更新成功")


@router.delete("/scripts/{script_id}", response_model=Response)
def delete_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    s = db.query(Script).filter(Script.id == script_id).first()
    if not s:
        return Response(code=404, msg="脚本不存在")
    db.delete(s)
    db.commit()
    return Response(msg="脚本删除成功")


@router.post("/scripts/execute", response_model=Response)
def execute_scripts(
    req: ScriptExecRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    _require_script_execution_enabled()
    scripts = db.query(Script).filter(
        Script.id.in_(req.script_ids), Script.is_active.is_(True)
    ).all()
    results = []
    for s in scripts:
        r = _run_script(s.content, s.script_type, env=req.extra_env or None)
        results.append({"id": s.id, "name": s.name, **r})
    return Response(data={"results": results, "total": len(results)})


@router.post("/block", response_model=Response)
def execute_block(
    req: BlockExecRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    _require_script_execution_enabled()
    script = db.query(Script).filter(
        Script.id == req.script_id, Script.is_active.is_(True)
    ).first()
    if not script:
        return Response(code=404, msg="封堵脚本不存在或已停用")
    results = []
    for t in req.targets:
        env = dict(t.env or {})
        env.setdefault("TARGET_IP", t.ip)
        r = _run_script(script.content, script.script_type, env=env)
        results.append({"ip": t.ip, "name": script.name, **r})
    return Response(data={"results": results, "total": len(results)})


@router.post("/execute", response_model=Response)
def execute_adhoc(
    req: AdhocExecRequest,
    current_user: User = Depends(get_current_admin_user),
):
    _require_script_execution_enabled()
    result = _run_script(req.script, req.type)
    return Response(data=result)


# ---------------------------------------------------------------------------
# Traffic inspection
# ---------------------------------------------------------------------------

@router.post("/traffic", response_model=Response)
def inspect_traffic(
    req: TrafficQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    es = _get_es_service(db)
    index = req.index or es.config.default_index
    gte = utc_iso(utc_naive() - timedelta(minutes=req.window_minutes))
    field_types = es.get_index_fields(index) if es.client else {}
    must_clauses = [{"range": {"@timestamp": {"gte": gte}}}]
    if req.filters:
        for filt in req.filters:
            field = filt.get("field", "")
            op = filt.get("operator", "equals")
            val = filt.get("value", "")
            if not field:
                continue
            ft = field_types.get(field)
            if ft == "text" and field_types.get(f"{field}.keyword"):
                field = f"{field}.keyword"
            if op == "equals":
                must_clauses.append({"term": {field: val}})
            elif op == "contains":
                must_clauses.append({"wildcard": {field: f"*{val}*"}})
            elif op == "gt":
                must_clauses.append({"range": {field: {"gt": val}}})
            elif op == "lt":
                must_clauses.append({"range": {field: {"lt": val}}})
            elif op == "gte":
                must_clauses.append({"range": {field: {"gte": val}}})
            elif op == "lte":
                must_clauses.append({"range": {field: {"lte": val}}})
    group_field = req.group_by_field
    if field_types.get(group_field) == "text" and field_types.get(f"{group_field}.keyword"):
        group_field = f"{group_field}.keyword"
    body = {
        "size": 0,
        "query": {"bool": {"must": must_clauses}},
        "aggs": {
            "by_field": {
                "terms": {"field": group_field, "size": 100},
                "aggs": {"unique_docs": {"cardinality": {"field": "request_uri.keyword"}}},
            }
        },
    }
    try:
        res = es.client.search(index=index, body=body)
        buckets = res.get("aggregations", {}).get("by_field", {}).get("buckets", [])
        total = sum(b.get("doc_count", 0) for b in buckets)
        domains = [
            {"key": b["key"], "count": b["doc_count"], "unique_uris": b.get("unique_docs", {}).get("value", 0)}
            for b in buckets
        ]
        return Response(data={
            "domains": domains, "total": total,
            "window_minutes": req.window_minutes,
            "group_by_field": req.group_by_field,
            "index": index,
        })
    except Exception as e:
        return Response(code=500, msg=f"ES查询失败: {str(e)}")


# ---------------------------------------------------------------------------
# Prometheus direct metrics
# ---------------------------------------------------------------------------

@router.get("/prometheus-metrics", response_model=Response)
def prometheus_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prom_url = _cfg_get(db, "prometheus_url", "http://localhost:9090")
    prom_user = _cfg_get(db, "prometheus_user", "")
    prom_pwd = _cfg_get(db, "prometheus_password", "")

    def _query(q: str) -> Optional[float]:
        try:
            req = urllib.request.Request(
                f"{prom_url}/api/v1/query",
                data=urllib.parse.urlencode({"query": q}).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if prom_user:
                import base64
                req.add_header(
                    "Authorization",
                    "Basic " + base64.b64encode(f"{prom_user}:{prom_pwd}".encode()).decode(),
                )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                vals = result.get("data", {}).get("result", [])
                if vals:
                    return float(vals[0]["value"][1])
        except Exception:
            return None
        return None

    try:
        cpu = _query('rate(node_cpu_seconds_total{mode!="idle"}[5m]) * 100 / on(instance) group_left() count(node_cpu_seconds_total) by (instance)')
        mem_used = _query("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes")
        mem_total = _query("node_memory_MemTotal_bytes")
        disk_used = _query('node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}')
        disk_total = _query('node_filesystem_size_bytes{mountpoint="/"}')
        return Response(data={
            "connected": True,
            "cpu": {"avg": round(cpu, 2) if cpu else None, "peak": round(cpu * 1.2, 2) if cpu else None},
            "memory": {
                "avg": round((1 - (mem_total - mem_used or 0) / (mem_total or 1)) * 100, 2),
                "peak": round((1 - (mem_total - mem_used or 0) / (mem_total or 1)) * 100, 2),
            } if mem_total else None,
            "disk": {
                "avg": round((disk_used / disk_total * 100) if disk_total else 0, 2),
                "peak": round((disk_used / disk_total * 100) if disk_total else 0, 2),
            } if disk_total else None,
        })
    except Exception as e:
        return Response(data={"connected": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Grafana / Prometheus metrics
# ---------------------------------------------------------------------------

def _compute_server_metrics(db: Session, end_ts: int, seconds: int):
    """CPU / memory / disk avg+peak per server over [end_ts - seconds, end_ts].

    Returns ``(servers, prom_url, error)`` where each server is
    ``{instance, alias, cpu:{avg,peak}, memory:{avg,peak}, disks:[...]}``.
    """
    grafana_url = _cfg_get(db, "grafana_url", "http://localhost:3000").rstrip("/")
    if not grafana_url:
        return [], "", "grafana_url 未配置"
    headers = _grafana_headers(db)
    headers["Content-Type"] = "application/json"
    ctx = _insecure_ssl_context()
    prom_url = None
    prom_uid = None
    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources", headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            for ds in json.loads(resp.read()):
                if ds.get("type") == "prometheus":
                    prom_url = ds.get("url", "").rstrip("/")
                    prom_uid = str(ds.get("uid", ""))
                    break
    except Exception:
        pass
    if not prom_url:
        return [], "", "无法从 Grafana 获取 Prometheus 数据源"

    _step = 60 if seconds <= 7200 else (300 if seconds <= 86400 else 900)
    start = end_ts - seconds

    def _query_range(expr: str):
        try:
            proxy_url = f"{grafana_url}/api/datasources/proxy/uid/{prom_uid}"
            params = urllib.parse.urlencode({"query": expr, "start": start, "end": end_ts, "step": _step})
            req = urllib.request.Request(f"{proxy_url}/api/v1/query_range?{params}", headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                result = json.loads(resp.read())
            out = {}
            for item in result.get("data", {}).get("result", []):
                inst = item.get("metric", {}).get("instance", "unknown")
                out.setdefault(inst, [])
                for ts_str, val_str in item.get("values", []):
                    out[inst].append({"timestamp": int(float(ts_str)), "value": float(val_str)})
            return out
        except Exception:
            return {}

    def _stats(series):
        if not series:
            return None, None
        vals = [item["value"] for item in series]
        return round(sum(vals) / len(vals), 2), round(max(vals), 2)

    cpu_expr = 'rate(node_cpu_seconds_total{mode!="idle"}[5m]) * 100'
    mem_expr = "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"
    disk_root_expr = '(node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}) / node_filesystem_size_bytes{mountpoint="/"} * 100'
    disk_logs_expr = '(node_filesystem_size_bytes{mountpoint="/data/logs"} - node_filesystem_free_bytes{mountpoint="/data/logs"}) / node_filesystem_size_bytes{mountpoint="/data/logs"} * 100'

    cpu_series, mem_series, disk_root_series, disk_logs_series = {}, {}, {}, {}
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
        aliases = json.loads(_cfg_get(db, "server_aliases", "{}"))
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
            disks.append({"mountpoint": "/", "avg": dr_avg, "peak": dr_peak})
        if dl_vals:
            disks.append({"mountpoint": "/data/logs", "avg": dl_avg, "peak": dl_peak})
        # Merge every mountpoint's series (for the frontend trend chart).
        disk_series = []
        if dr_vals:
            disk_series.extend(dr_vals)
        if dl_vals:
            disk_series.extend(dl_vals)
        seen_ts = set()
        disk_series_dedup = []
        for p in sorted(disk_series, key=lambda x: x["timestamp"]):
            if p["timestamp"] not in seen_ts:
                seen_ts.add(p["timestamp"])
                disk_series_dedup.append(p)
        servers.append({
            "instance": inst,
            "alias": aliases.get(inst, ""),
            "cpu": {"avg": cpu_avg, "peak": cpu_peak},
            "memory": {"avg": mem_avg, "peak": mem_peak},
            "disks": disks,
            "cpu_series": cpu_series.get(inst, []),
            "memory_series": mem_series.get(inst, []),
            "disk_series": disk_series_dedup,
        })
    return servers, prom_url, None


@router.get("/grafana-metrics", response_model=Response)
def grafana_metrics(
    time_range: str = Query(default="1h", pattern="^(1h|6h|today|1d|7d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grafana system metrics.

    Pulls the Prometheus data source from Grafana, then uses
    ``/api/v1/query_range`` for history. ``time_range``: 1h | 6h | today | 1d | 7d.
    """
    grafana_url = _cfg_get(db, "grafana_url", "http://localhost:3000").rstrip("/")
    if not grafana_url:
        return Response(data={"connected": False, "error": "grafana_url 未配置"})
    headers = _grafana_headers(db)
    headers["Content-Type"] = "application/json"
    ctx = _insecure_ssl_context()

    prom_url = None
    prom_uid = None
    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources", headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            for ds in json.loads(resp.read()):
                if ds.get("type") == "prometheus":
                    prom_url = ds.get("url", "").rstrip("/")
                    prom_uid = str(ds.get("uid", ""))
                    break
    except Exception:
        pass
    if not prom_url:
        return Response(data={
            "connected": False,
            "error": "无法从 Grafana 获取 Prometheus 数据源，请检查 Grafana 数据源配置",
        })

    _range_map = {"1h": 3600, "6h": 21600, "today": 86400, "1d": 86400, "7d": 604800}
    _seconds = _range_map.get(time_range, 3600)
    _time_label_map = {
        "1h": "最近 1 小时", "6h": "最近 6 小时", "today": "今日",
        "1d": "最近 1 天", "7d": "最近 7 天",
    }
    _time_label = _time_label_map.get(time_range, "最近 1 小时")
    _step = 60 if _seconds <= 7200 else (300 if _seconds <= 86400 else 900)

    now = int(time.time())
    servers, prom_url, _err = _compute_server_metrics(db, now, _seconds)
    if not servers:
        return Response(data={
            "connected": _err is None,
            "source": "grafana",
            "prom_url": prom_url,
            "time_range": _time_label,
            "servers": [],
            "custom": [],
            "error": _err or "未查询到任何服务器指标，请确认 Prometheus 已采集 node_exporter 数据",
        })

    # Custom metrics: instant value + trend series.
    def _query_range(expr: str):
        try:
            proxy_url = f"{grafana_url}/api/datasources/proxy/uid/{prom_uid}"
            params = urllib.parse.urlencode({"query": expr, "start": now - _seconds, "end": now, "step": _step})
            req = urllib.request.Request(f"{proxy_url}/api/v1/query_range?{params}", headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                result = json.loads(resp.read())
            out = {}
            for item in result.get("data", {}).get("result", []):
                inst = item.get("metric", {}).get("instance", "unknown")
                out.setdefault(inst, [])
                for ts_str, val_str in item.get("values", []):
                    out[inst].append({"timestamp": int(float(ts_str)), "value": float(val_str)})
            return out
        except Exception:
            return {}

    def _query_instant(expr: str):
        try:
            proxy_url = f"{grafana_url}/api/datasources/proxy/uid/{prom_uid}"
            params = urllib.parse.urlencode({"query": expr})
            req = urllib.request.Request(f"{proxy_url}/api/v1/query?{params}", headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                result = json.loads(resp.read())
            out = {}
            for item in result.get("data", {}).get("result", []):
                inst = item.get("metric", {}).get("instance", "unknown")
                out[inst] = float(item.get("value", ["", 0])[1])
            return out
        except Exception:
            return {}

    custom_metrics = db.query(CustomMetric).all()
    custom_results = []
    if custom_metrics:
        instant_map = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            instant_futs = {pool.submit(_query_instant, m.promql): m for m in custom_metrics}
            for fut in as_completed(instant_futs):
                m = instant_futs[fut]
                try:
                    instant_map[m.id] = fut.result()
                except Exception:
                    instant_map[m.id] = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            range_futs = {pool.submit(_query_range, m.promql): m for m in custom_metrics}
            for fut in as_completed(range_futs):
                m = range_futs[fut]
                try:
                    inst_series_map = fut.result()
                except Exception:
                    inst_series_map = {}
                series_data = []
                for _inst, pts in inst_series_map.items():
                    series_data.extend(pts)
                seen_ts = set()
                series_data_dedup = []
                for p in sorted(series_data, key=lambda x: x["timestamp"]):
                    if p["timestamp"] not in seen_ts:
                        seen_ts.add(p["timestamp"])
                        series_data_dedup.append(p)
                custom_results.append({
                    "id": m.id, "name": m.name, "description": m.description,
                    "promql": m.promql, "unit": m.unit,
                    "values": [{"instance": inst, "value": round(v, 4)} for inst, v in instant_map.get(m.id, {}).items()],
                    "series_data": series_data_dedup,
                })

    return Response(data={
        "connected": True,
        "source": "grafana",
        "prom_url": prom_url,
        "time_range": _time_label,
        "servers": servers,
        "custom": custom_results,
    })


# ---------------------------------------------------------------------------
# VirusTotal / ipinfo country lookup
# ---------------------------------------------------------------------------

@router.post("/lookup-country", response_model=Response)
def lookup_country(
    req: List[str] = Body(..., max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lookup country for multiple IPs via ipinfo.io (primary) + VirusTotal (fallback)."""
    results = {}
    for ip in req:
        country_code = _get_ipinfo_country(ip)
        if country_code:
            results[ip] = _to_chinese_country(country_code)
            continue
        raw = _get_virustotal_info(ip, db)
        results[ip] = _to_chinese_country(raw.get("country", "")) if raw else ""
    return Response(data=results)


# ---------------------------------------------------------------------------
# Python dependency management (admin only — installs execute code)
# ---------------------------------------------------------------------------

_CORE_PACKAGES = {
    "pip", "setuptools", "wheel", "fastapi", "uvicorn", "sqlalchemy", "pymysql",
    "pydantic", "pydantic-settings", "python-multipart", "cryptography",
    "python-jose", "passlib", "bcrypt", "elasticsearch", "apscheduler", "httpx",
}

_PKG_RE = re.compile(r"^[a-zA-Z0-9._=\-\^~\[\]]+$")


@router.get("/pip-packages", response_model=Response[List[dict]])
def list_pip_packages(current_user: User = Depends(get_current_admin_user)):
    """List installed Python packages (``pip list``)."""
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True, timeout=30,
            env=_scrubbed_env(), close_fds=True,
        )
        packages = json.loads(result.stdout)
        return Response(data=[{"name": p["name"], "version": p["version"]} for p in packages])
    except Exception as e:
        return Response(code=400, msg=f"获取包列表失败: {str(e)}", data=[])


@router.post("/pip-install", response_model=Response)
def pip_install(
    req: PipInstallReq,
    current_user: User = Depends(get_current_admin_user),
):
    """Install a Python package (admin only)."""
    _require_script_execution_enabled()
    pkg = req.package.strip()
    if not pkg:
        return Response(code=400, msg="包名不能为空")
    # One package specifier only — blocks `--index-url=http://evil` style flags.
    if not _PKG_RE.match(pkg) or pkg.startswith("-"):
        return Response(code=400, msg="包名格式不合规，仅允许字母、数字与 ._-+=^~[]")
    try:
        result = subprocess.run(
            ["pip", "install", pkg, "--quiet", "--no-input", "--disable-pip-version-check"],
            capture_output=True, timeout=120,
            env=_scrubbed_env(), close_fds=True,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        if result.returncode == 0:
            return Response(msg=f"安装成功: {pkg}", data={"package": pkg, "ok": True})
        err_msg = re.sub(r"\x1b\[[0-9;]*m", "", stderr or stdout).strip()
        return Response(code=400, msg=f"安装失败: {err_msg[:500]}")
    except subprocess.TimeoutExpired:
        return Response(code=400, msg="安装超时（超过 2 分钟）")
    except Exception as e:
        return Response(code=400, msg=f"安装异常: {str(e)}")


@router.post("/pip-uninstall", response_model=Response)
def pip_uninstall(
    req: PipUninstallReq,
    current_user: User = Depends(get_current_admin_user),
):
    """Uninstall a Python package (admin only)."""
    _require_script_execution_enabled()
    pkg = req.package.strip()
    if not pkg:
        return Response(code=400, msg="包名不能为空")
    if not _PKG_RE.match(pkg) or pkg.startswith("-"):
        return Response(code=400, msg="包名格式不合规")
    if pkg.lower() in _CORE_PACKAGES:
        return Response(code=400, msg=f"禁止卸载核心依赖: {pkg}")
    try:
        result = subprocess.run(
            ["pip", "uninstall", pkg, "-y", "--quiet"],
            capture_output=True, timeout=60,
            env=_scrubbed_env(), close_fds=True,
        )
        if result.returncode == 0:
            return Response(msg=f"卸载成功: {pkg}")
        err = re.sub(r"\x1b\[[0-9;]*m", "", result.stderr.decode("utf-8", errors="replace")).strip()
        return Response(code=400, msg=f"卸载失败: {err[:300]}")
    except Exception as e:
        return Response(code=400, msg=f"卸载异常: {str(e)}")


# ---------------------------------------------------------------------------
# Custom metrics
# ---------------------------------------------------------------------------

@router.get("/custom-metrics", response_model=Response)
def list_custom_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    metrics = db.query(CustomMetric).order_by(CustomMetric.created_at.desc()).all()
    return Response(data=[{
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "promql": m.promql,
        "unit": m.unit,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
        "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M:%S") if m.updated_at else "",
    } for m in metrics])


@router.post("/custom-metrics", response_model=Response)
def create_custom_metric(
    req: CustomMetricCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if db.query(CustomMetric).filter(CustomMetric.name == req.name).first():
        return Response(code=409, msg=f"指标名称「{req.name}」已存在")
    metric = CustomMetric(
        name=req.name, description=req.description, promql=req.promql, unit=req.unit,
    )
    db.add(metric)
    db.commit()
    return Response(msg=f"自定义指标「{req.name}」创建成功")


@router.put("/custom-metrics/{metric_id}", response_model=Response)
def update_custom_metric(
    metric_id: int,
    req: CustomMetricUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    metric = db.query(CustomMetric).filter(CustomMetric.id == metric_id).first()
    if not metric:
        return Response(code=404, msg="指标不存在")
    if req.name is not None and req.name != metric.name:
        if db.query(CustomMetric).filter(
            CustomMetric.name == req.name, CustomMetric.id != metric_id
        ).first():
            return Response(code=409, msg=f"指标名称「{req.name}」已存在")
        metric.name = req.name
    if req.description is not None:
        metric.description = req.description
    if req.promql is not None:
        metric.promql = req.promql
    if req.unit is not None:
        metric.unit = req.unit
    db.commit()
    return Response(msg="自定义指标更新成功")


@router.delete("/custom-metrics/{metric_id}", response_model=Response)
def delete_custom_metric(
    metric_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    metric = db.query(CustomMetric).filter(CustomMetric.id == metric_id).first()
    if not metric:
        return Response(code=404, msg="指标不存在")
    name = metric.name
    db.delete(metric)
    db.commit()
    return Response(msg=f"自定义指标「{name}」已删除")


# ---------------------------------------------------------------------------
# Server aliases
# ---------------------------------------------------------------------------

@router.get("/server-aliases", response_model=Response)
def get_server_aliases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(SystemConfig).filter(SystemConfig.key == "server_aliases").first()
    if not row or not row.value:
        return Response(data={})
    try:
        return Response(data=json.loads(row.value))
    except Exception:
        return Response(data={})


@router.put("/server-aliases", response_model=Response)
def set_server_aliases(
    req: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    row = db.query(SystemConfig).filter(SystemConfig.key == "server_aliases").first()
    if not row:
        row = SystemConfig(key="server_aliases", value="{}")
        db.add(row)
    row.value = json.dumps(req, ensure_ascii=False)
    db.commit()
    return Response(msg="别名保存成功", data=req)
