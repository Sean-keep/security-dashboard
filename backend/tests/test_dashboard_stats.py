"""首页概览聚合接口。

前端 ``getDashboardStats`` 先打 ``GET /dashboard/stats``；它 404 时才会退回三个
旧端点。契约一断，首页三张卡就全挂 —— 所以这里把形状钉死。
"""
from tests.conftest import login_headers


def test_dashboard_stats_shape(client):
    h = login_headers(client)
    resp = client.get("/api/dashboard/stats", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    d = body["data"]
    assert set(d) >= {"address_count", "rule_count", "alert", "trend"}
    assert isinstance(d["address_count"], int)
    assert isinstance(d["rule_count"], int)
    assert set(d["alert"]) >= {"total", "today", "critical", "high", "pending", "trend"}
    assert len(d["trend"]) == 7
    assert set(d["trend"][0]) == {"date", "count"}


def test_dashboard_stats_requires_auth(client):
    assert client.get("/api/dashboard/stats").status_code in (401, 403)


def test_dashboard_matches_alert_stats(client):
    """两处统计必须同源，否则首页卡片和告警页会对不上。"""
    h = login_headers(client)
    dash = client.get("/api/dashboard/stats", headers=h).json()["data"]
    alert = client.get("/api/alerts/stats", headers=h).json()["data"]
    assert dash["alert"]["total"] == alert["total"]
    assert dash["trend"] == alert["trend"]


def test_rule_list_accepts_page_size_1(client):
    """回退路径拼装时用 page_size=1 —— 历史下限 ge=10 会把它打回 422。"""
    h = login_headers(client)
    resp = client.get("/api/rules?page_size=1", headers=h)
    assert resp.status_code == 200, resp.text
