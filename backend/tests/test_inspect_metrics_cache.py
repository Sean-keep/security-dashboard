"""系统监控（/inspect/grafana-metrics）的缓存：30 秒内不重跑，refresh=1 强制穿透。

这一段慢是硬伤 —— Grafana 在远端，单趟往返地板价 ~810ms，一次页面加载要 4~5 趟。
所以这里锁三件事：
  1. 同一个时间范围 30 秒内重复请求不重跑 Grafana；
  2. `refresh=1` 必须穿透（「刷新」按钮和保存别名走这条）；
  3. 不同时间范围是**独立的**缓存槽位，切范围不能吃到对方的旧数据。
另锁 `_discover_prometheus` 自己的 5 分钟缓存 —— 原先一次页面加载要查两遍
`/api/datasources`（grafana_metrics 和 _compute_server_metrics 各一次）。
"""
import json
import urllib.parse

import pytest

import app.api.inspect as insp
from tests.conftest import login_headers


@pytest.fixture(autouse=True)
def _clear_metrics_cache():
    insp._METRICS_CACHE.clear()
    yield
    insp._METRICS_CACHE.clear()


def _patch_fake_grafana(monkeypatch):
    """把 Grafana 全部堵掉，只数被调了几次。返回计数字典。"""
    calls = {"disco": 0, "compute": 0}

    def _disco(db):
        calls["disco"] += 1
        return "http://prom:9090", "uid-1", None

    def _compute(db, now, seconds):
        calls["compute"] += 1
        return [{"instance": "web-01", "cpu": {"avg": 1.0, "peak": 2.0}}], "http://prom:9090", None

    monkeypatch.setattr(insp, "_discover_prometheus", _disco)
    monkeypatch.setattr(insp, "_compute_server_metrics", _compute)
    return calls


def test_repeat_request_hits_cache(client, monkeypatch):
    """30 秒内两次同样的请求：第二次不能重跑 Grafana，返回值还得一样。"""
    calls = _patch_fake_grafana(monkeypatch)
    h = login_headers(client)

    first = client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    assert first.status_code == 200
    assert first.json()["code"] == 200
    assert calls["compute"] == 1

    second = client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    assert second.json()["code"] == 200
    assert calls["compute"] == 1, f"缓存没生效，又跑了 Grafana（compute={calls['compute']}）"
    assert second.json()["data"] == first.json()["data"]


def test_refresh_bypasses_cache(client, monkeypatch):
    """「刷新」按钮传 refresh=1 —— 不穿透的话用户点刷新看到的还是旧数据。"""
    calls = _patch_fake_grafana(monkeypatch)
    h = login_headers(client)

    client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    assert calls["compute"] == 1

    resp = client.get("/api/inspect/grafana-metrics?time_range=1h&refresh=1", headers=h)
    assert resp.json()["code"] == 200
    assert calls["compute"] == 2, "refresh=1 必须强制重跑"

    # 穿透之后写回的是新数据，紧接着的普通请求又走缓存
    client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    assert calls["compute"] == 2


def test_cache_slot_is_per_time_range(client, monkeypatch):
    """1h / 6h 是两个槽位 —— 切时间范围要是吃到对方的缓存，图就串了。"""
    calls = _patch_fake_grafana(monkeypatch)
    h = login_headers(client)

    a = client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    b = client.get("/api/inspect/grafana-metrics?time_range=6h", headers=h)
    assert calls["compute"] == 2
    assert a.json()["data"]["time_range"] != b.json()["data"]["time_range"]

    # 回到 1h 仍是缓存命中
    client.get("/api/inspect/grafana-metrics?time_range=1h", headers=h)
    assert calls["compute"] == 2


def test_discover_prometheus_caches_datasource_lookup(db_session, monkeypatch):
    """/api/datasources 一次页面加载本来要查两遍 —— 结果缓 5 分钟就够。"""
    hits = {"n": 0}

    class _Resp:
        def read(self):
            return json.dumps([{"type": "prometheus", "uid": "p1", "url": "http://prom:9090/"}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=0, context=None):
        hits["n"] += 1
        return _Resp()

    monkeypatch.setattr(insp, "_cfg_get", lambda db, key, default="": "http://grafana:3000/")
    monkeypatch.setattr(insp, "_grafana_headers", lambda db: {"Authorization": "Bearer x"})
    monkeypatch.setattr(insp, "_insecure_ssl_context", lambda: None)
    monkeypatch.setattr(insp.urllib.request, "urlopen", _urlopen)
    insp._DISCO_CACHE.clear()

    try:
        url1, uid1, err1 = insp._discover_prometheus(db_session)
        url2, uid2, err2 = insp._discover_prometheus(db_session)
    finally:
        insp._DISCO_CACHE.clear()

    assert err1 is None and err2 is None
    assert uid1 == uid2 == "p1"
    assert url1 == url2 == "http://prom:9090", "URL 末尾斜杠要 rstrip 掉"
    assert hits["n"] == 1, f"/api/datasources 查了 {hits['n']} 遍，缓存没生效"
