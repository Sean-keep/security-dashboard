"""告警 CSV 导出：路由不被 /{alert_id} 吞掉、筛选一致、Excel 可读。"""
from tests.conftest import login_headers


def _make_alert(db_session, **kw):
    from app.models.alert import Alert

    defaults = dict(
        title="攻击告警",
        content="来自 1.2.3.4 的扫描",
        src_ip="1.2.3.4",
        dst_ip="5.6.7.8",
        severity="high",
        status="pending",
        category="scan",
        rule_name="高频攻击",
        event_count=3,
    )
    defaults.update(kw)
    alert = Alert(**defaults)
    db_session.add(alert)
    db_session.commit()
    return alert


def test_export_requires_auth(client):
    client.cookies.clear()
    resp = client.get("/api/alerts/export")
    assert resp.status_code == 401


def test_export_is_not_shadowed_by_alert_id(client, admin_user, db_session):
    """/alerts/export 必须命中导出路由，而不是把 "export" 当 int 解析成 422。"""
    _make_alert(db_session)
    headers = login_headers(client)
    resp = client.get("/api/alerts/export", headers=headers)
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]


def test_export_csv_has_bom_and_chinese_headers(client, admin_user, db_session):
    _make_alert(db_session, content="多行\n内容")
    headers = login_headers(client)
    resp = client.get("/api/alerts/export", headers=headers)

    text = resp.content.decode("utf-8")
    assert text.startswith("﻿"), "缺 BOM，Excel 会把中文显示成乱码"
    first_line = text.lstrip("﻿").splitlines()[0]
    assert "告警标题" in first_line
    assert "触发规则" in first_line
    # 自由文本换行不能打断行
    assert len(text.lstrip("﻿").splitlines()) == 2


def test_export_respects_filters(client, admin_user, db_session):
    _make_alert(db_session, title="匹配我", severity="critical")
    _make_alert(db_session, title="别导我", severity="low")
    headers = login_headers(client)

    text = client.get("/api/alerts/export?keyword=匹配我", headers=headers).content.decode("utf-8")
    assert "匹配我" in text and "别导我" not in text

    text = client.get("/api/alerts/export?severity=critical", headers=headers).content.decode("utf-8")
    assert "匹配我" in text and "别导我" not in text


def test_export_and_list_agree_on_filters(client, admin_user, db_session):
    """「导出的就是当前筛出来的」—— 两个端点共用同一条筛选路径。"""
    _make_alert(db_session, title="A", severity="high")
    _make_alert(db_session, title="B", severity="low")
    _make_alert(db_session, title="C", severity="high")
    headers = login_headers(client)

    listed = client.get("/api/alerts?severity=high", headers=headers).json()["data"]["total"]
    exported = client.get("/api/alerts/export?severity=high", headers=headers).content.decode("utf-8")
    # 表头 1 行 + listed 行
    assert len(exported.lstrip("﻿").splitlines()) == listed + 1
    assert listed == 2


def test_export_excludes_raw_logs_columns(client, admin_user, db_session):
    """raw_logs 是 ES 原始日志 JSON，塞进 CSV 会把文件撑爆。"""
    _make_alert(db_session, raw_log='{"huge": true}', raw_logs='[{"a":1},{"b":2}]')
    headers = login_headers(client)
    text = client.get("/api/alerts/export", headers=headers).content.decode("utf-8")
    header = text.lstrip("﻿").splitlines()[0]
    assert "raw_log" not in header
    assert "raw_logs" not in header
    assert "huge" not in text
