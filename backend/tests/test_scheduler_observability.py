"""调度器可观测性与调度参数校验。

钉住这批行为：
  1. 保存时校验调度参数 —— 错 cron 不能「保存成功然后永远不跑」；
  2. scheduler_* 是运行态，不该出现在 GET /settings/config 上被人改；
  3. rules.py 那个假的 /rules/scheduler/status 已经删掉；
  4. 预览和保存走同一条解析路径；
  5. 执行日志带 duration_ms / triggered_by，status 支持 missed；
  6. /metrics 手写 Prometheus 文本，不引依赖。
"""
from datetime import timedelta

from tests.conftest import login_headers


def _rule_payload(name="r1", schedule_type="interval", schedule_value="5 minutes"):
    return {
        "name": name,
        "description": "",
        "stages": [],
        "nodes": [],
        "es_index": "security-logs-*",
        "schedule_type": schedule_type,
        "schedule_value": schedule_value,
        "is_enabled": True,
        "actions": [],
    }


# ── 1. 保存时校验调度参数 ────────────────────────────────────────────


def test_create_rule_rejects_bad_cron(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="cron", schedule_value="99 * * * *"),
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "cron" in body["msg"].lower() or "Cron" in body["msg"] or "99" in body["msg"]


def test_create_rule_rejects_bad_interval(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="interval", schedule_value="every hour"),
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_create_rule_rejects_zero_interval(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="interval", schedule_value="0 minutes"),
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_create_rule_accepts_valid_schedule(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="interval", schedule_value="5 minutes"),
        headers=h,
    )
    assert resp.json()["code"] == 200


def test_create_rule_once_needs_no_value(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="once", schedule_value=""),
        headers=h,
    )
    assert resp.json()["code"] == 200


def test_update_rule_rejects_bad_cron(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    created = client.post("/api/rules", json=_rule_payload(), headers=h).json()
    rid = created["data"]["id"]

    resp = client.put(
        f"/api/rules/{rid}",
        json={"schedule_type": "cron", "schedule_value": "0 99 * * *"},
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_update_rule_validates_combined_fields(client, admin_user):
    """只提交 schedule_value 的 PUT 里 schedule_type 是 None ——
    校验必须拿「更新后的」组合，不能拿本次载荷里的 None 去判。"""
    h = login_headers(client, "admin", "AdminPass1")
    created = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="cron", schedule_value="0 9 * * *"),
        headers=h,
    ).json()
    rid = created["data"]["id"]

    resp = client.put(f"/api/rules/{rid}", json={"schedule_value": "5 minutes"}, headers=h)
    # type 仍是 cron，value 变成 "5 minutes" → 不是合法 cron
    assert resp.json()["code"] == 400


# ── 2. 运行态键不进配置页 ────────────────────────────────────────────


def test_scheduler_heartbeat_not_exposed_in_config(client, admin_user, db_session):
    from app.models.config import SystemConfig

    db_session.add(SystemConfig(
        key="scheduler_heartbeat", value="2026-09-24T10:00:00",
        label="scheduler_heartbeat", description="", group_name="general",
    ))
    db_session.add(SystemConfig(
        key="scheduler_dirty", value="1",
        label="scheduler_dirty", description="", group_name="runtime",
    ))
    db_session.commit()

    h = login_headers(client, "admin", "AdminPass1")
    data = client.get("/api/settings/config", headers=h).json()["data"]
    flat = {item["key"] for arr in data.values() for item in arr}
    assert "scheduler_heartbeat" not in flat
    assert "scheduler_dirty" not in flat
    assert "runtime" not in data


def test_cannot_write_runtime_key_via_save_config(client, admin_user, db_session):
    from app.models.config import SystemConfig

    db_session.add(SystemConfig(
        key="scheduler_heartbeat", value="2026-09-24T10:00:00",
        label="scheduler_heartbeat", description="", group_name="runtime",
    ))
    db_session.commit()

    h = login_headers(client, "admin", "AdminPass1")
    resp = client.put(
        "/api/settings/config",
        json={"updates": {"scheduler_heartbeat": "2000-01-01T00:00:00"}},
        headers=h,
    )
    assert resp.json()["code"] == 400


# ── 3. 假状态接口已删 ────────────────────────────────────────────────


def test_lie_scheduler_status_route_is_gone(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.get("/api/rules/scheduler/status", headers=h)
    assert resp.status_code == 404


def test_real_scheduler_status_reports_problems(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    resp = client.get("/api/scheduler/status", headers=h)
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    # 测试环境从没起过调度器 → 不健康，且要说清为什么
    assert data["running"] is False
    assert data["healthy"] is False
    assert any("心跳" in p for p in data["problems"])


# ── 4. 预览与保存同一条路径 ──────────────────────────────────────────


def test_schedule_preview_matches_save_validation(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")

    ok = client.post(
        "/api/rules/schedule-preview",
        json={"schedule_type": "cron", "schedule_value": "0 9 * * *", "count": 1},
        headers=h,
    ).json()["data"]
    assert ok["valid"] is True
    assert len(ok["next_runs"]) == 1

    bad = client.post(
        "/api/rules/schedule-preview",
        json={"schedule_type": "cron", "schedule_value": "99 * * * *"},
        headers=h,
    ).json()["data"]
    assert bad["valid"] is False
    assert bad["error"]

    # 同一个表达式保存也必须被拒 —— 两套逻辑分叉就是 bug
    resp = client.post(
        "/api/rules",
        json=_rule_payload(schedule_type="cron", schedule_value="99 * * * *"),
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_schedule_preview_interval_and_once(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")

    iv = client.post(
        "/api/rules/schedule-preview",
        json={"schedule_type": "interval", "schedule_value": "5 minutes", "count": 2},
        headers=h,
    ).json()["data"]
    assert iv["valid"] is True
    assert len(iv["next_runs"]) == 2

    once = client.post(
        "/api/rules/schedule-preview",
        json={"schedule_type": "once", "schedule_value": ""},
        headers=h,
    ).json()["data"]
    assert once["valid"] is True
    assert once["next_runs"] == []
    assert "手动" in (once.get("note") or "")


def test_parse_schedule_unit_cases():
    from app.services.rule_runner import ScheduleError, parse_schedule, preview_schedule

    assert parse_schedule("once", "") is None

    trig = parse_schedule("interval", "5 minutes")
    assert trig is not None
    assert parse_schedule("interval", "1 hours") is not None
    assert parse_schedule("interval", "2 days") is not None

    for bad in ["", "5", "0 minutes", "-1 minutes", "5 parsecs", "five minutes"]:
        try:
            parse_schedule("interval", bad)
        except ScheduleError:
            pass
        else:
            raise AssertionError(f"interval {bad!r} 本该被拒")

    assert parse_schedule("cron", "17 3 * * *") is not None
    for bad in ["", "99 * * * *", "0 9 * *", "0 9 * * * *"]:
        try:
            parse_schedule("cron", bad)
        except ScheduleError:
            pass
        else:
            raise AssertionError(f"cron {bad!r} 本该被拒")

    # preview 故意不抛
    p = preview_schedule("cron", "not a cron")
    assert p["valid"] is False
    assert p["next_runs"] == []


def test_next_runs_are_monotonic():
    from app.services.rule_runner import next_runs, parse_schedule

    trig = parse_schedule("cron", "*/15 * * * *")
    runs = next_runs(trig, 3)
    assert len(runs) == 3
    assert runs[0] < runs[1] < runs[2]
    # 同一个 fire time 不该原地打转
    assert len({r.isoformat() for r in runs}) == 3


# ── 5. 执行日志的耗时 / 触发来源 / 漏跑 ──────────────────────────────


def test_execution_log_carries_duration_and_trigger(client, admin_user, db_session):
    from app.services.rule_executor import record_execution_log

    record_execution_log(
        db_session,
        rule_id=1,
        rule_name="r",
        alert_count=2,
        detail={"trigger": "manual"},
        status="success",
        duration_ms=1234,
        triggered_by="manual",
    )

    h = login_headers(client, "admin", "AdminPass1")
    rows = client.get("/api/execution-logs", headers=h).json()["data"]["list"]
    assert rows
    row = rows[0]
    assert row["duration_ms"] == 1234
    assert row["triggered_by"] == "manual"
    assert row["status"] == "success"


def test_missed_run_is_recorded(db_session):
    from app.models.execution_log import RuleExecutionLog
    from app.services.rule_runner import record_missed_run

    # 必须把 session 注进去 —— 不传的话它会开 SessionLocal() 写到另一个库去
    record_missed_run(42, rule_name="错过的人", reason="错过触发窗口（测试）", db=db_session)

    rows = (
        db_session.query(RuleExecutionLog)
        .filter(RuleExecutionLog.rule_id == 42)
        .all()
    )
    assert rows
    assert rows[0].status == "missed"
    assert rows[0].triggered_by == "scheduler"
    assert "错过" in (rows[0].error_message or "")


def test_status_filter_includes_missed(client, admin_user, db_session):
    from app.services.rule_executor import record_execution_log

    record_execution_log(
        db_session, rule_id=7, rule_name="x", status="missed",
        error_message="错过触发窗口", duration_ms=0, triggered_by="scheduler",
    )

    h = login_headers(client, "admin", "AdminPass1")
    rows = client.get(
        "/api/execution-logs", params={"rule_id": 7, "status": "missed"}, headers=h
    ).json()["data"]["list"]
    assert rows and rows[0]["status"] == "missed"


# ── 6. 健康接口 ──────────────────────────────────────────────────────


def test_scheduler_health_reports_counts(client, admin_user, db_session):
    from app.services.rule_executor import record_execution_log

    record_execution_log(
        db_session, rule_id=1, rule_name="a", status="success",
        duration_ms=10, triggered_by="scheduler",
    )
    record_execution_log(
        db_session, rule_id=1, rule_name="a", status="missed",
        error_message="错过", duration_ms=0, triggered_by="scheduler",
    )

    h = login_headers(client, "admin", "AdminPass1")
    data = client.get("/api/scheduler/health", headers=h).json()["data"]
    assert data["counts_24h"]["success"] >= 1
    assert data["counts_24h"]["missed"] >= 1
    assert data["running"] is False
    assert data["problems"]


# ── 7. /metrics ──────────────────────────────────────────────────────


def test_metrics_prometheus_text(client, admin_user):
    h = login_headers(client, "admin", "AdminPass1")
    # 登录只为拿 token？不 —— /metrics 不走 Bearer，走 query token（或开放）。
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "scheduler_up" in body
    assert "scheduler_heartbeat_age_seconds" in body
    assert "scheduler_jobs" in body
    assert "rule_runs_24h" in body
    assert "# TYPE scheduler_up gauge" in body


def test_metrics_token_gate(client, admin_user, db_session):
    from app.models.config import SystemConfig

    db_session.add(SystemConfig(
        key="metrics_token", value="s3cret", label="metrics_token",
        description="", group_name="security",
    ))
    db_session.commit()

    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics?token=wrong").status_code == 403
    ok = client.get("/metrics?token=s3cret")
    assert ok.status_code == 200
    assert "scheduler_up" in ok.text


# ── 8. 脏标记 ────────────────────────────────────────────────────────


def test_mark_and_consume_dirty_flag():
    from app.services.scheduler_service import SchedulerService

    assert SchedulerService.consume_dirty() in (True, False)  # 先清干净
    SchedulerService.mark_dirty()
    assert SchedulerService.consume_dirty() is True
    assert SchedulerService.consume_dirty() is False


def test_create_rule_sets_dirty_flag(client, admin_user):
    from app.services.scheduler_service import SchedulerService

    SchedulerService.consume_dirty()
    h = login_headers(client, "admin", "AdminPass1")
    client.post("/api/rules", json=_rule_payload(name="dirty-probe"), headers=h)
    assert SchedulerService.consume_dirty() is True
