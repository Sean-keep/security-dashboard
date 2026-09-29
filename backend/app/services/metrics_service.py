"""
Grafana / Prometheus 指标查询 —— 指标规则的数据入口。

为什么不复用 `api/inspect.py`：那里的查询逻辑是三处函数闭包（`_compute_server_metrics`、
`grafana_metrics` 里的 `_query_range` / `_query_instant`），各自内联了 url 拼装和响应
解析，拆不出来；`api/settings.py` 又把 `_grafana_headers` 抄了一遍。按「只抽新服务、
不动现有代码」的取舍，这里独立写一份，**不要回头去改那两处** —— 等哪天它们真要重构，
可以换成调这里。

为什么用 stdlib `urllib` 而不是 httpx：规则执行跑在两个解释器里（web 用 venv 的
python，调度器用系统 python3.10），而 `rule_runner` 的模块头已经写明「不要引入
requirements 之外的依赖」。容器的 venv 也从不被 deploy.sh 同步，加依赖 = 线上直接起不来。

请求套路（Grafana 数据源代理）：
    GET {grafana_url}/api/datasources
        → 取第一个 type=="prometheus" 的 uid
    GET {grafana_url}/api/datasources/proxy/uid/{uid}/api/v1/query?query={expr}
        → data.result = [{"metric": {...标签}, "value": [ts, "值"]}]
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_QUERY_TIMEOUT = 5.0


# ── 传输 ──────────────────────────────────────────────────────────


def insecure_ssl_context():
    """跳过证书校验的 SSL context。

    只给内网自签证书的 Grafana/Prometheus 用。**刻意保持「总是不校验」**，
    与 `api/inspect.py` 的同名函数行为一致 —— 那边虽然注释说受
    `grafana_verify_certs` 控制，实际从没读过那个开关。这里不要「顺手修好」，
    改校验策略属于行为变更，得单独立项。
    """
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _cfg_get(db, key: str, default: str = "") -> str:
    from app.models.config import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row else default


def grafana_headers(db) -> Dict[str, str]:
    """Grafana 请求头（API Key / Basic Auth + 浏览器 UA）。

    UA 必须带 —— Grafana 前面挂 CDN/代理时，没有浏览器 UA 会被直接 403。
    """
    auth_mode = _cfg_get(db, "grafana_auth_mode", "apikey")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    if auth_mode == "basic":
        user = _cfg_get(db, "grafana_user", "")
        pwd = _cfg_get(db, "grafana_password", "")
        if user and pwd:
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {**headers, "Authorization": f"Basic {token}"}
    else:
        api_key = _cfg_get(db, "grafana_api_key", "")
        if api_key:
            return {**headers, "Authorization": f"Bearer {api_key}"}
    return headers


def grafana_url(db) -> str:
    return (_cfg_get(db, "grafana_url", "") or "").rstrip("/")


# ── 返回结构 ──────────────────────────────────────────────────────


@dataclass
class Series:
    """一条 Prometheus series。labels 是完整标签集 —— 规则要按它给每台机器单独计时。"""

    labels: Dict[str, str] = field(default_factory=dict)
    value: Optional[float] = None
    ts: Optional[float] = None


@dataclass
class QueryResult:
    ok: bool = False
    series: List[Series] = field(default_factory=list)
    error: Optional[str] = None


# ── 查询 ──────────────────────────────────────────────────────────


def discover_prometheus(db) -> Tuple[str, str, Optional[str]]:
    """找出 Grafana 里的 Prometheus 数据源。返回 ``(prom_url, uid, error)``。

    每次现查而不缓存：一分钟两次 HTTP 往返不算开销，而缓存要考虑数据源改名/删除
    的失效面。和 `inspect.py` 现有行为一致。
    """
    url = grafana_url(db)
    if not url:
        return "", "", "未配置 Grafana 地址（系统设置 → grafana_url）"
    headers = grafana_headers(db)
    ctx = insecure_ssl_context()
    try:
        req = urllib.request.Request(f"{url}/api/datasources", headers=headers)
        with urllib.request.urlopen(req, timeout=_QUERY_TIMEOUT, context=ctx) as resp:
            datasources = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return "", "", (
                f"Grafana 认证失败（HTTP {exc.code}）——请检查系统设置里的 "
                "grafana_auth_mode / API Key / 账号密码"
            )
        return "", "", f"Grafana /api/datasources 返回 HTTP {exc.code}"
    except Exception as exc:
        return "", "", f"连接 Grafana 失败: {type(exc).__name__}: {exc}"

    for ds in datasources if isinstance(datasources, list) else []:
        if ds.get("type") == "prometheus":
            return (
                str(ds.get("url", "")).rstrip("/"),
                str(ds.get("uid", "")),
                None,
            )
    return "", "", "Grafana 里没有 Prometheus 数据源"


def query_instant(db, expr: str, timeout: float = _QUERY_TIMEOUT) -> QueryResult:
    """跑一次 PromQL instant 查询，返回所有 series 的当前值。

    **失败不抛异常**，返回 ``ok=False`` + 人话 ``error`` —— 指标规则把「查不到数据」
    当成正常情况跳过（不误报、不判规则失败），调用方拿到的是结果不是异常。
    """
    expr = (expr or "").strip()
    if not expr:
        return QueryResult(ok=False, error="PromQL 表达式为空")

    _prom_url, uid, err = discover_prometheus(db)
    if err:
        return QueryResult(ok=False, error=err)

    url = grafana_url(db)
    params = urllib.parse.urlencode({"query": expr})
    target = f"{url}/api/datasources/proxy/uid/{uid}/api/v1/query?{params}"
    headers = grafana_headers(db)
    ctx = insecure_ssl_context()
    try:
        req = urllib.request.Request(target, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return QueryResult(ok=False, error=f"PromQL 查询返回 HTTP {exc.code} {detail}".strip())
    except Exception as exc:
        return QueryResult(ok=False, error=f"PromQL 查询失败: {type(exc).__name__}: {exc}")

    if not isinstance(payload, dict):
        return QueryResult(ok=False, error="PromQL 返回了非 JSON 对象")
    if payload.get("status") not in (None, "success"):
        return QueryResult(ok=False, error=f"PromQL 执行失败: {payload.get('error') or payload.get('status')}")

    raw = (payload.get("data") or {}).get("result") or []
    series: List[Series] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") or {}
        if not isinstance(labels, dict):
            labels = {}
        labels = {str(k): str(v) for k, v in labels.items()}
        val: Optional[float] = None
        ts: Optional[float] = None
        pair = item.get("value")
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            try:
                ts = float(pair[0])
            except (TypeError, ValueError):
                ts = None
            val = _to_float(pair[1])
        series.append(Series(labels=labels, value=val, ts=ts))
    return QueryResult(ok=True, series=series)


def _to_float(raw) -> Optional[float]:
    """Prometheus 的值是字符串，NaN / +Inf 也会照实送过来。

    这里只做类型转换，**不滤 NaN** —— 让上层自己决定「NaN 算不算一次观测」，
    这样两边的语义写在一处。
    """
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def series_key(labels: Dict[str, str]) -> str:
    """标签集的稳定指纹。同一条 series 反复查询必须得到同一个 key。

    用 ``sort_keys`` 的规范 JSON 做 sha1 —— 标签顺序在不同查询/不同版本里
    不保证一致，直接拼字符串会把同一条 series 算成好几条。
    """
    canonical = json.dumps(labels or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def is_usable(value: Optional[float]) -> bool:
    """NaN / None 都不算一次有效观测 —— 既不触发告警也不算「掉下阈值」。"""
    return value is not None and not (isinstance(value, float) and math.isnan(value))
