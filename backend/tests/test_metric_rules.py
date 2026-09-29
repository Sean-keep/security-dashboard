"""
指标阈值规则 —— 「条件连续成立满 N 分钟」的状态机与结果行契约。

钉住三件事：
  1. **语义**：是「持续」不是「均值」。尖峰后掉下去不能触发；中途掉下阈值要重新计时。
  2. **状态跨运行存活**：计时在库里，不在进程里。两次独立的 evaluate 必须接着算。
  3. **结果行契约**：`RuleExecutor` 读 `src_ip`/`count`/`start_time`…，多条 series
     必须产生互相独立的告警（指纹带 src_ip）。

时间用「回拨已落库的时间戳」推进，不引 freezegun —— 和仓库里其他测试一致，
而且这样「跨运行存活」是天然成立的：每次 evaluate 都是一次全新的调用。
"""
import json
from datetime import timedelta

from app.utils.timezone import local_now
from tests.conftest import login_headers


# ── 夹具 ──────────────────────────────────────────────────────────

def _cfg(promql="up", operator=">", threshold=80, sustain_minutes=5):
    return json.dumps({
        "promql": promql,
        "operator": operator,
        "threshold": threshold,
        "duration_seconds": sustain_minutes * 60,
    }, ensure_ascii=False)


def _make_rule(db_session, *, source_type="metric", actions=None, enabled=True,
               promql="up", operator=">", threshold=80, sustain_minutes=5):
    from app.models.rule import Rule

    if actions is None:
        actions = [{"type": "create_alert", "severity": "high"}]
    rule = Rule(
        name="CPU 持续高",
        description="",
        nodes="[]", stages="[]", output_mapping="{}",
        es_index="",
        source_type=source_type,
        metric_config=_cfg(promql, operator, threshold, sustain_minutes) if source_type == "metric" else "{}",
        schedule_type="interval", schedule_value="60 seconds",
        is_enabled=enabled,
        actions=json.dumps(actions, ensure_ascii=False),
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def _qr(*pairs):
    """`_qr(({...labels}, value), ...)` → 一次成功的 QueryResult。"""
    from app.services.metrics_service import QueryResult, Series

    return QueryResult(ok=True, series=[
        Series(labels=dict(labels), value=value) for labels, value in pairs
    ])


def _fail(msg="Grafana 连接被拒绝"):
    from app.services.metrics_service import QueryResult

    return QueryResult(ok=False, error=msg)


def _patch_query(monkeypatch, result):
    from app.services import metrics_service

    monkeypatch.setattr(
        metrics_service, "query_instant", lambda db, expr, **kw: result
    )
    return result


def _rewind(db_session, rule_id, *, breach_age=None, check_age=None):
    """把已落库的状态时间戳往前拨 —— 测试里推进时间的家常做法。

    截到整秒：引擎写 `breach_since` 也是整秒（MySQL 的 DATETIME 只有秒精度），
    两边精度不一致会让「整 5 分钟」差那几毫秒而判不成立。
    """
    from app.models.metric_rule_state import RuleMetricState

    now = local_now().replace(microsecond=0)
    for st in db_session.query(RuleMetricState).filter(RuleMetricState.rule_id == rule_id).all():
        if breach_age is not None and st.breach_since is not None:
            st.breach_since = now - breach_age
        if check_age is not None and st.last_check_at is not None:
            st.last_check_at = now - check_age
    db_session.commit()


def _states(db_session, rule_id):
    from app.models.metric_rule_state import RuleMetricState

    return (
        db_session.query(RuleMetricState)
        .filter(RuleMetricState.rule_id == rule_id)
        .all()
    )


def _evaluate(db_session, rule):
    from app.services import metric_rule_engine

    return metric_rule_engine.evaluate_metric_rule(db_session, rule)


def _fake_telegram(monkeypatch):
    from app.services import telegram_notify as tn

    calls = []

    def _send(bot_token, chat_id, text, **kw):
        calls.append(text)
        return True, ""

    monkeypatch.setattr(tn, "send_telegram", _send, raising=True)
    monkeypatch.setattr(
        "app.services.telegram_notify.send_telegram", _send, raising=True
    )
    return calls


# ── 状态机：「持续」的语义 ─────────────────────────────────────────


def test_breach_must_hold_for_full_duration(db_session, monkeypatch):
    """成立但还没凑满时长 → 不触发；满 5 分钟才触发。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    out = _evaluate(db_session, rule)
    assert out.rows == []
    assert out.breaching == 1

    # 成立了 4 分钟：还不够
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=4))
    out = _evaluate(db_session, rule)
    assert out.rows == []

    # 5 分钟整：触发
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=5))
    out = _evaluate(db_session, rule)
    assert len(out.rows) == 1
    assert out.rows[0]["value"] == 87.0


def test_breach_reset_on_dip(db_session, monkeypatch):
    """中途掉下阈值 → 计时清零，重新成立要再等满一个窗口。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=4))

    # 掉下去一次
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 50.0)))
    out = _evaluate(db_session, rule)
    assert out.rows == []
    st = _states(db_session, rule.id)[0]
    assert st.breach_since is None

    # 又超了，只过了 1 分钟 —— 不能凭旧计时直接触发
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)
    assert out.rows == []


def test_not_avg_over_time_semantics(db_session, monkeypatch):
    """尖峰后立刻掉下 → 不触发。这钉死了「不是 5 分钟均值」这个语义。

    如果实现写成 `avg_over_time(cpu[5m]) > 80`，一个 100 的尖峰会把均值顶上去
    然后照样触发 —— 那是错的。
    """
    rule = _make_rule(db_session, sustain_minutes=5)

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 100.0)))
    _evaluate(db_session, rule)
    # 把计时拨到「差一点就满」
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=4, seconds=59))

    # 尖峰掉下去
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 10.0)))
    out = _evaluate(db_session, rule)
    assert out.rows == []


def test_state_survives_across_evaluations(db_session, monkeypatch):
    """两次独立的 evaluate 接着算 —— 计时不能只活在调用栈里。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    _evaluate(db_session, rule)
    # 回拨之后再调一次 —— 这是一次全新的函数调用，没有闭包、没有模块级变量
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=5))
    out = _evaluate(db_session, rule)
    assert len(out.rows) == 1


def test_gap_beyond_grace_restarts_streak(db_session, monkeypatch):
    """观测断档超过宽限 → 重新计时。

    断档那一小时里到底成不成立没人知道，凭旧时间戳宣称「已持续 5 分钟」是
    拿没观测到的时段当证据。宁可漏报。
    """
    from app.services.metric_rule_engine import GRACE_SECONDS

    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)

    _rewind(
        db_session, rule.id,
        breach_age=timedelta(minutes=10),
        check_age=timedelta(seconds=GRACE_SECONDS + 60),
    )
    out = _evaluate(db_session, rule)
    assert out.rows == []
    st = _states(db_session, rule.id)[0]
    # 计时重新从这次观测起算
    assert st.breach_since is not None
    assert (local_now() - st.breach_since).total_seconds() < 5


def test_fire_once_per_streak_then_reemit(db_session, monkeypatch):
    """持续中的告警每分钟都产出结果行，交给去重冷却压噪音（与 ES 规则一致）。"""
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)
    assert len(out.rows) == 1

    # 还在告警中：继续产出（去重层决定推不推 TG）
    out = _evaluate(db_session, rule)
    assert len(out.rows) == 1
    assert out.rows[0]["sustained_seconds"] >= 60


def test_nan_series_is_no_data_and_closes_alert(db_session, monkeypatch):
    """没取到值 = 这次没上报：既撑不起「持续」，也不该让告警挂着关不掉。

    以前把 NaN 当「序列还在」原样跳过 —— 实测连续 5 轮 NaN 之后 `recovered=0`、
    告警一直是 `pending`，接口一停流就永远关不掉。文案也要说实话：不是「已恢复」
    （那是真回落了），是「已恢复（数据中断）」。
    """
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    from app.services import rule_runner
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    assert db_session.query(Alert).one().status == "pending"

    # 接口这一分钟没流量 → histogram_quantile 对全 0 桶返回 NaN，series 还在结果里
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, float("nan"))))
    out = _evaluate(db_session, rule)

    assert out.rows == [], "没数据不该产出「又命中了」的结果行"
    assert out.recovered == 1
    assert out.no_data is True
    assert out.recoveries[0]["recovery_reason"] == "数据中断", "NaN 不是回落，是没观测"
    alert = db_session.query(Alert).one()
    assert alert.status == "auto_resolved"
    assert any("已恢复（数据中断）" in t for t in tg), tg
    assert _states(db_session, rule.id) == []


def test_nan_series_not_firing_is_silent(db_session, monkeypatch):
    """没告警就断观测 → 只清状态，一条通知都不发。本来也没什么要撤回的。"""
    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)   # 开始计时，未触发

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, float("nan"))))
    out = _evaluate(db_session, rule)
    assert out.recovered == 0
    assert out.no_data is True
    assert tg == []
    assert _states(db_session, rule.id) == []


def test_all_nan_result_closes_every_series(db_session, monkeypatch):
    """整个查询返回的序列都没取到值 → 按「没数据」记账，同时把在响的都关掉。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, 87.0),
        ({"instance": "web-02"}, 95.0),
    ))
    from app.services import rule_runner
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    assert db_session.query(Alert).count() == 2

    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, float("nan")),
        ({"instance": "web-02"}, float("nan")),
    ))
    out = _evaluate(db_session, rule)

    assert out.no_data is True
    assert out.recovered == 2
    assert out.rows == []
    assert {a.status for a in db_session.query(Alert).all()} == {"auto_resolved"}
    assert sum("已恢复（数据中断）" in t for t in tg) == 2, tg
    assert _states(db_session, rule.id) == []


def test_only_valueless_series_is_closed(db_session, monkeypatch):
    """一批 series 里只断了一条：只关那一条，其它照常计时。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, 87.0),
        ({"instance": "web-02"}, 95.0),
    ))
    from app.services import rule_runner
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, float("nan")),   # 这条停流了
        ({"instance": "web-02"}, 95.0),           # 这条还在超阈值
    ))
    out = _evaluate(db_session, rule)

    assert out.recovered == 1
    assert out.no_data is False, "还有 series 取到值，不算「无数据」"
    assert out.series_seen == 1
    assert out.series_no_value == 1, "日志要能看出来被丢了几条 —— 只报有值的就看不出收了多少"
    detail = out.to_detail()
    assert detail["series_no_value"] == 1
    assert detail["series_seen"] == 1
    assert "无取值" in detail.get("note", ""), "执行摘要要说清楚有几条被当成了没数据"
    assert [r["src_ip"] for r in out.rows] == ["web-02"], "还在响的那条得继续产出结果行"
    assert sum("已恢复（数据中断）" in t for t in tg) == 1, tg
    assert {a.src_ip: a.status for a in db_session.query(Alert).all()} == {
        "web-01": "auto_resolved",
        "web-02": "pending",
    }
    left = _states(db_session, rule.id)
    assert len(left) == 1, "只该删掉没数据的那条状态"
    assert "web-02" in left[0].series_labels
    assert left[0].firing == 1


def test_no_data_gap_breaks_sustain(db_session, monkeypatch):
    """「持续」只能由**收到的**观测撑起来 —— 中间断一次就得重新计时。

    否则空档能充数：明明中间那一轮什么都没观测到，还宣称「已持续 2 分钟」。
    """
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)                                    # 计时开始
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))   # 已经「成立 1 分钟」
    before_gap = _states(db_session, rule.id)[0].breach_since

    # 中间插一次「没数据」。要是它没把计时打断，下一行就该触发了。
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, float("nan"))))
    _evaluate(db_session, rule)
    assert _states(db_session, rule.id) == [], "没数据就当没数据，状态清掉"

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    out = _evaluate(db_session, rule)

    assert out.rows == [], "断档把「连续」打断了，不该接着原来的计时凑满时长"
    st = _states(db_session, rule.id)[0]
    assert st.breach_since is not None
    assert st.breach_since > before_gap, "断档后计时必须从头开始，不能接着原来那个起点"


# ── 恢复通知 ──────────────────────────────────────────────────────


def test_recovery_only_after_firing(db_session, monkeypatch):
    """没凑满时长就回落 → **不**发「已恢复」。本来就没告警过，发了是噪音。"""
    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=2))

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 10.0)))
    out = _evaluate(db_session, rule)
    assert out.recovered == 0
    assert not any("已恢复" in t for t in tg)


def test_recovery_emits_and_closes_alert(db_session, monkeypatch):
    """已告警后回落 → 发「已恢复」并把告警关成 resolved。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    from app.services import rule_runner
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 1 and alerts[0].status == "pending"
    assert any("持续" in t or "CPU" in t for t in tg)

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 10.0)))
    out = _evaluate(db_session, rule)
    assert out.recovered == 1

    db_session.refresh(alerts[0])
    # 是「自动恢复」不是「已解决」—— 后者是人处理完的，混在一起就看不出谁关的单
    assert alerts[0].status == "auto_resolved"
    assert alerts[0].resolved_at is not None
    assert any("已恢复" in t for t in tg)


def test_recovery_goes_to_recoveries_not_rows(db_session, monkeypatch):
    """恢复行进 `outcome.recoveries`；`outcome.rows` 只放「又命中了」。

    这条边界是防「低于阈值反而告警」的关键：`rows` 会被原样喂给
    `process_actions`，而那里不认识 recovery，一律当新命中开单。
    """
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    fired = _evaluate(db_session, rule)
    assert len(fired.rows) == 1, "命中行才是结果行"

    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 10.0)))
    out = _evaluate(db_session, rule)

    assert out.rows == [], "恢复行混进 rows 就会被当成新命中"
    assert len(out.recoveries) == 1
    assert out.recoveries[0]["recovery"] is True
    assert out.recoveries[0]["value"] == 10.0
    assert out.recovered == 1


def test_recovery_must_not_open_a_new_alert(db_session, monkeypatch):
    """回落那一行是「关单」不是「又命中」——漏进 process_actions 会再开一条。

    实测出过：阈值 >5s 的 P95 掉到 4.8125s，反而开出一条新告警，内容里还留着
    没渲染的 `{sustain_minutes}`（因为恢复行没有那个键，是它的指纹特征）。
    """
    from app.models.alert import Alert
    from app.services import rule_runner

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], threshold=5, sustain_minutes=1)

    # 先真告警一条（6.25 > 5）
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/v1/x"}, 6.25)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    assert db_session.query(Alert).count() == 1

    # P95 掉回阈值以下。整条恢复走 run_rule —— 泄漏就发生在这条路上。
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/v1/x"}, 4.8125)))
    res = rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 1, (
        f"回落不该再开单，实际 {len(alerts)} 条 —— "
        "第二条就是低于阈值的恢复行被当成了命中"
    )
    assert alerts[0].status == "auto_resolved"
    assert res.total == 0, "恢复行不该被算成结果行"
    assert any("已恢复" in t for t in tg)


def test_auto_resolved_is_distinct_from_human_resolved(db_session, monkeypatch, client, admin_user):
    """系统关的单和人关的单必须分得开 —— 表里没有 resolved_by，全靠 status。

    「已解决」读起来像人处理完了。指标回落要是也写成 resolved，就再也分不出
    哪条是自己好的、哪条真被人处理过。
    """
    from app.models.alert import Alert
    from app.services import rule_runner

    rule = _make_rule(db_session, threshold=5, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/pay"}, 6.25)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    opened = db_session.query(Alert).one()

    # 人工点「解决」→ resolved
    resp = client.put(f"/api/alerts/{opened.id}", json={"status": "resolved"}, headers=login_headers(client))
    assert resp.status_code == 200
    db_session.refresh(opened)
    assert opened.status == "resolved"
    assert opened.resolved_at is not None

    # 指标回落自动关单 → auto_resolved，绝不能是 resolved
    rule2 = _make_rule(db_session, threshold=5, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/pay"}, 6.25)))
    _evaluate(db_session, rule2)
    _rewind(db_session, rule2.id, breach_age=timedelta(minutes=1))
    rule_runner.run_rule(db_session, rule2.id, triggered_by="manual")
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/pay"}, 1.0)))
    _evaluate(db_session, rule2)

    closed = db_session.query(Alert).filter(Alert.rule_id == rule2.id).one()
    assert closed.status == "auto_resolved", f"回落自动关单不该写成 {closed.status}"


def test_vanished_series_firing_gets_data_gap_recovery(db_session, monkeypatch):
    """series 消失且已在告警 → 关告警 + 发「已恢复（数据中断）」，文案说实话。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    from app.services import rule_runner
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    # 整个 series 不见了（exporter 挂了 / 实例下线）
    _patch_query(monkeypatch, _qr())
    out = _evaluate(db_session, rule)
    assert out.recovered == 1

    alert = db_session.query(Alert).one()
    assert alert.status == "auto_resolved"
    assert any("数据中断" in t for t in tg)
    assert _states(db_session, rule.id) == []


def test_vanished_series_not_firing_is_silent(db_session, monkeypatch):
    """没告警就消失 → 只删状态，一条通知都不发。"""
    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)   # 开始计时，未触发

    _patch_query(monkeypatch, _qr())
    out = _evaluate(db_session, rule)
    assert out.recovered == 0
    assert tg == []
    assert _states(db_session, rule.id) == []


# ── 结果行契约 ────────────────────────────────────────────────────


def test_distinct_series_distinct_fingerprints(db_session, monkeypatch):
    """两台机器同时超阈值 = 两条独立告警、两次推送（指纹带 src_ip）。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, 87.0),
        ({"instance": "web-02"}, 95.0),
    ))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))

    from app.services import rule_runner
    out = rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 2
    assert len({a.fingerprint for a in alerts}) == 2
    assert {a.src_ip for a in alerts} == {"web-01", "web-02"}
    assert out.alert_count == 2
    assert len([t for t in tg if "🟢" not in t]) == 2


def test_metric_row_keys_match_executor_contract(db_session, monkeypatch):
    """结果行必须带 `_claim` / `_write_mysql` 要读的那些键，单位也要对。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01:9100", "job": "node"}, 87.3)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=5))
    out = _evaluate(db_session, rule)
    row = out.rows[0]

    for key in ("src_ip", "count", "start_time", "end_time", "duration",
                "value", "threshold", "operator", "promql"):
        assert key in row, f"缺少 {key}"
    # instance + job 都是身份标签，拼全才不会跟同机另一个 job 撞车
    assert row["src_ip"] == "web-01:9100/node"
    assert row["count"] == 1
    # _write_mysql: datetime.fromtimestamp(x/1000) —— 必须是 epoch **毫秒**
    from datetime import datetime
    assert datetime.fromtimestamp(row["start_time"] / 1000) < datetime.fromtimestamp(row["end_time"] / 1000)
    assert row["duration"] == 300
    assert row["sustain_minutes"] == 5


def test_identity_uses_route_for_histogram_rules(db_session, monkeypatch):
    """`by (le, route)` 只剩 route 标签 —— 身份要认得出是哪个接口，不能退化成 series-xxx。"""
    rule = _make_rule(db_session, threshold=5, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"route": "/v1/login/get_otp"}, 10.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)

    from app.services.metric_rule_engine import identity_of
    assert identity_of({"route": "/v1/login/get_otp"}, "abc") == "/v1/login/get_otp"
    assert out.rows[0]["src_ip"] == "/v1/login/get_otp"


def test_identity_composite_when_multiple_identity_labels(db_session, monkeypatch):
    """`by (le, instance, route)` 下两个接口同机 —— 身份必须拼全，否则合并成一条告警。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, threshold=5, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(
        ({"instance": "10.0.0.1:9032", "route": "/a"}, 9.0),
        ({"instance": "10.0.0.1:9032", "route": "/b"}, 8.0),
    ))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    from app.services import rule_runner
    out = rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 2
    assert {a.src_ip for a in alerts} == {"10.0.0.1:9032/a", "10.0.0.1:9032/b"}
    assert out.alert_count == 2
    assert len(tg) == 2


def test_identity_includes_job_so_service_is_visible():
    """`sum by (le, job, route)` 下要认得出是哪个服务在告警 —— job 必须进身份。"""
    from app.services.metric_rule_engine import identity_of

    assert identity_of({"job": "20k_ospay_api", "route": "/v1/login/verify_otp"}, "k") \
        == "20k_ospay_api/v1/login/verify_otp"
    assert identity_of({"job": "20k_ospay_api"}, "k") == "20k_ospay_api"
    # 两个 job 同名接口必须是两个身份，不能合并成一条告警
    assert identity_of({"job": "api_a", "route": "/pay"}, "k") \
        != identity_of({"job": "api_b", "route": "/pay"}, "k")


def test_identity_falls_back_to_series_key():
    """一个身份标签都没有时才退到 series_key；namespace/app 只是兜底。"""
    from app.services.metric_rule_engine import identity_of

    assert identity_of({"namespace": "prod"}, "k") == "prod"
    assert identity_of({"app": "web"}, "k") == "web"
    assert identity_of({}, "abcdefghij123456") == "series-abcdefghij12"
    # 机器维度优先于接口维度 —— 更具体
    assert identity_of({"instance": "a:9100", "route": "/x"}, "k") == "a:9100/x"


def test_breach_since_is_whole_seconds(db_session, monkeypatch):
    """`breach_since` 必须落成整秒。

    MySQL 的 DATETIME 只有秒精度且**四舍五入**：11:55:52.9 存进去变 11:55:53，
    下一轮 `now - breach_since` 就只有 59.9 秒，「持续 1 分钟」要多等整整一个
    周期才响。实测就是 1 分钟规则花了 2 分钟。写入前先截到整秒就没有这个漂移。
    """
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    from app.services.metric_rule_engine import evaluate_metric_rule
    now = local_now().replace(microsecond=900000)   # 人为带 0.9 秒
    evaluate_metric_rule(db_session, rule, now=now)

    st = _states(db_session, rule.id)[0]
    assert st.breach_since.microsecond == 0
    assert st.breach_since == now.replace(microsecond=0)


def test_one_minute_rule_fires_on_the_second_check(db_session, monkeypatch):
    """连续两次检查（间隔 60 秒）就该响，不能拖到第三次。"""
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    from app.services.metric_rule_engine import evaluate_metric_rule
    base = local_now().replace(microsecond=900000)
    assert evaluate_metric_rule(db_session, rule, now=base).rows == []
    out = evaluate_metric_rule(db_session, rule, now=base + timedelta(minutes=1))
    assert len(out.rows) == 1


def test_template_fields_render(db_session, monkeypatch):
    """模板里的 {instance} / {value} / {threshold} 要能填出来。"""
    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.5)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)

    from app.services.rule_executor import render_alert_template
    text = render_alert_template(
        "{instance} 现在 {value}，阈值 {operator}{threshold}", out.rows[0]
    )
    assert text == "web-01 现在 87.5，阈值 >80.0"


def test_template_renders_nested_dict_fields(db_session, monkeypatch):
    """`{labels.route}` 要取到 labels 里的值，不能把占位符原样留在标题里。

    模板引擎的 `{a.b}` 本来只认阶段名（`_stages`），指标行的 labels 是个 dict，
    于是 `{labels.route}` 一直渲染成字面量，告警标题上就是一串花括号。
    """
    rule = _make_rule(db_session, threshold=5, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/v1/x"}, 6.25)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)

    from app.services.rule_executor import render_alert_template
    text = render_alert_template(
        "{labels.route}的 P95 达到 {value}s，已持续 {sustain_minutes} 分钟", out.rows[0]
    )
    assert text == "/v1/x的 P95 达到 6.25s，已持续 1 分钟"

    # 取不到的键仍然是字面量，不该抛异常也不该填 None
    assert render_alert_template("{labels.nope}", out.rows[0]) == "{labels.nope}"


def test_template_accepts_grafana_go_syntax(db_session, monkeypatch):
    """`{{$labels.route}}` / `{{ $value }}` 是 Grafana 的 Go 模板，写 PromQL 规则时
    会一起抄过来 —— 得能用，不能在标题里留一堆花括号。"""
    rule = _make_rule(db_session, threshold=5, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"job": "api", "route": "/pay"}, 6.25)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))
    out = _evaluate(db_session, rule)

    from app.services.rule_executor import render_alert_template
    assert render_alert_template(
        "{{$labels.route}}的 P95 达到 {{ $value }}s", out.rows[0]
    ) == "/pay的 P95 达到 6.25s"
    # 不带 $、花括号里带空格的写法也要认（用户实测就是这么写的）
    assert render_alert_template(
        "{{labels.job }}的 P95 超阈值: {labels.route}", out.rows[0]
    ) == "api的 P95 超阈值: /pay"


def test_metric_rule_never_touches_es(db_session, monkeypatch):
    """指标规则不能构造 ESService —— 指标专用的机器上 ES 可能根本没配。"""
    from app.services import rule_runner

    rule = _make_rule(db_session, sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))

    # 真去连 ES 会炸（库里一行 es_* 配置都没有）
    result = rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    assert result.status == "success", result.error
    assert result.total == 1


# ── 无数据：不误报、不算失败 ──────────────────────────────────────


def test_no_data_is_success_not_failure(db_session, monkeypatch):
    """Grafana 不可达 → status=success、0 告警，执行日志记「无数据」。"""
    from app.models.execution_log import RuleExecutionLog
    from app.services import rule_runner

    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _fail())

    result = rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    assert result.status == "success", result.error
    assert result.total == 0
    assert result.alert_count == 0

    log = db_session.query(RuleExecutionLog).order_by(RuleExecutionLog.id.desc()).first()
    assert log.status == "success"
    detail = json.loads(log.detail)
    assert detail.get("no_data") is True
    assert "无数据" in detail.get("note", "")


def test_query_failure_does_not_touch_state(db_session, monkeypatch):
    """查询失败一行状态都不写 —— 抖一下不该重置计时，也不该误判消失。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    before = _states(db_session, rule.id)[0]
    before_key = before.series_key
    before_breach = before.breach_since

    _patch_query(monkeypatch, _fail())
    out = _evaluate(db_session, rule)
    assert out.no_data is True
    st = _states(db_session, rule.id)[0]
    assert st.series_key == before_key
    assert st.breach_since == before_breach


def test_empty_result_is_no_data(db_session, monkeypatch):
    """查询成功但没有序列 → 记「无数据」，不告警、不判失败。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr())
    out = _evaluate(db_session, rule)
    assert out.no_data is True
    assert out.rows == []


def test_cooldown_suppresses_repeat_push(db_session, monkeypatch):
    """持续告警每分钟都产出，但冷却窗口里只抬计数、不刷 TG。"""
    from app.models.alert import Alert

    tg = _fake_telegram(monkeypatch)
    rule = _make_rule(db_session, actions=[
        {"type": "create_alert", "severity": "high"},
        {"type": "telegram", "bot_token": "T", "chat_id": "C"},
    ], sustain_minutes=1)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    _rewind(db_session, rule.id, breach_age=timedelta(minutes=1))

    from app.services import rule_runner
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")
    rule_runner.run_rule(db_session, rule.id, triggered_by="manual")

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].event_count >= 3
    # 只有跃迁那次推 TG
    assert len([t for t in tg if "🟢" not in t]) == 1


# ── 校验 / 生命周期 ───────────────────────────────────────────────


def test_metric_rule_forces_60s_schedule(client, admin_user, db_session):
    headers = login_headers(client)
    resp = client.post("/api/rules", json={
        "name": "CPU 高", "source_type": "metric",
        "metric": {"promql": "up", "operator": ">", "threshold": 80, "sustain_minutes": 5},
        "schedule_type": "cron", "schedule_value": "0 9 * * *",
        "actions": [{"type": "create_alert"}],
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["schedule_type"] == "interval"
    assert data["schedule_value"] == "60 seconds"
    assert data["source_type"] == "metric"
    assert data["metric"]["sustain_minutes"] == 5


def test_metric_rule_rejects_missing_promql(client, admin_user, db_session):
    headers = login_headers(client)
    resp = client.post("/api/rules", json={
        "name": "x", "source_type": "metric",
        "metric": {"promql": "  ", "operator": ">", "threshold": 1, "sustain_minutes": 5},
    }, headers=headers)
    body = resp.json()
    assert body["code"] == 400
    assert "PromQL" in body["msg"]


def test_metric_rule_rejects_bad_operator(client, admin_user, db_session):
    headers = login_headers(client)
    resp = client.post("/api/rules", json={
        "name": "x", "source_type": "metric",
        "metric": {"promql": "up", "operator": "!=", "threshold": 1, "sustain_minutes": 5},
    }, headers=headers)
    assert resp.status_code == 422   # pydantic 的 pattern 直接拒掉


def test_metric_rule_rejects_zero_sustain(client, admin_user, db_session):
    headers = login_headers(client)
    resp = client.post("/api/rules", json={
        "name": "x", "source_type": "metric",
        "metric": {"promql": "up", "operator": ">", "threshold": 1, "sustain_minutes": 0},
    }, headers=headers)
    assert resp.status_code == 422


def test_metric_rule_rejects_nonempty_stages(client, admin_user, db_session):
    headers = login_headers(client)
    resp = client.post("/api/rules", json={
        "name": "x", "source_type": "metric",
        "metric": {"promql": "up", "operator": ">", "threshold": 1, "sustain_minutes": 5},
        "stages": [{"id": "s1", "index": "security-logs-*"}],
    }, headers=headers)
    body = resp.json()
    assert body["code"] == 400
    assert "查询阶段" in body["msg"]


def test_metric_rule_create_and_get_roundtrip(client, admin_user, db_session):
    headers = login_headers(client)
    created = client.post("/api/rules", json={
        "name": "CPU 高", "source_type": "metric",
        "metric": {"promql": "rate(x[5m])", "operator": ">=", "threshold": 12.5, "sustain_minutes": 3},
        "actions": [{"type": "create_alert"}],
    }, headers=headers).json()["data"]

    got = client.get(f"/api/rules/{created['id']}", headers=headers).json()["data"]
    assert got["source_type"] == "metric"
    assert got["metric"]["promql"] == "rate(x[5m])"
    assert got["metric"]["operator"] == ">="
    assert got["metric"]["threshold"] == 12.5
    assert got["metric"]["duration_seconds"] == 180

    # 日志规则不受影响
    logs_rule = client.post("/api/rules", json={
        "name": "日志规则", "stages": [{"id": "s1", "index": "security-logs-*"}],
    }, headers=headers).json()["data"]
    assert logs_rule["source_type"] == "logs"
    assert logs_rule["metric"] is None


def test_config_change_or_disable_or_delete_clears_state(db_session, monkeypatch):
    """条件变了 / 停用 / 删除 → 计时状态必须清掉。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))
    _evaluate(db_session, rule)
    assert len(_states(db_session, rule.id)) == 1

    from app.services import metric_rule_engine
    metric_rule_engine.clear_rule_states(db_session, rule.id)
    assert _states(db_session, rule.id) == []


def test_config_change_clears_state_via_api(client, admin_user, db_session, monkeypatch):
    from app.models.metric_rule_state import RuleMetricState

    headers = login_headers(client)
    created = client.post("/api/rules", json={
        "name": "CPU 高", "source_type": "metric",
        "metric": {"promql": "up", "operator": ">", "threshold": 80, "sustain_minutes": 5},
    }, headers=headers).json()["data"]

    db_session.add(RuleMetricState(
        rule_id=created["id"], series_key="abc", series_labels="{}",
        breach_since=local_now(), firing=1, last_value=99.0, last_check_at=local_now(),
    ))
    db_session.commit()

    # 改阈值 → 旧计时器作废（拿旧证据判新标准是错的）
    resp = client.put(f"/api/rules/{created['id']}", json={
        "metric": {"promql": "up", "operator": ">", "threshold": 70, "sustain_minutes": 5},
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    assert (
        db_session.query(RuleMetricState)
        .filter(RuleMetricState.rule_id == created["id"])
        .count()
    ) == 0


def test_delete_rule_removes_state_rows(client, admin_user, db_session):
    from app.models.metric_rule_state import RuleMetricState

    headers = login_headers(client)
    created = client.post("/api/rules", json={
        "name": "CPU 高", "source_type": "metric",
        "metric": {"promql": "up", "operator": ">", "threshold": 80, "sustain_minutes": 5},
    }, headers=headers).json()["data"]
    db_session.add(RuleMetricState(
        rule_id=created["id"], series_key="abc", series_labels="{}",
        breach_since=local_now(), firing=1, last_value=99.0, last_check_at=local_now(),
    ))
    db_session.commit()

    assert client.delete(f"/api/rules/{created['id']}", headers=headers).status_code == 200
    assert (
        db_session.query(RuleMetricState)
        .filter(RuleMetricState.rule_id == created["id"])
        .count()
    ) == 0


# ── 只读预览 ──────────────────────────────────────────────────────


def test_preview_does_not_advance_streak(db_session, monkeypatch):
    """点「测试」不能把持续计时往前推，否则会莫名其妙提前触发。"""
    rule = _make_rule(db_session, sustain_minutes=5)
    _patch_query(monkeypatch, _qr(({"instance": "web-01"}, 87.0)))

    from app.services import metric_rule_engine
    snap = metric_rule_engine.preview_metric_rule(db_session, rule)
    assert snap["total"] == 1
    assert snap["preview"][0]["breaching"] is True
    assert snap["preview"][0]["firing"] is False
    # 一个字都没写进状态表
    assert _states(db_session, rule.id) == []


def test_promql_test_endpoint(client, admin_user, db_session, monkeypatch):
    headers = login_headers(client)
    _patch_query(monkeypatch, _qr(
        ({"instance": "web-01"}, 1.0),
        ({"instance": "web-02"}, 1.0),
    ))
    resp = client.post("/api/rules/promql-test", json={"promql": "up"}, headers=headers)
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 2
    assert {s["identity"] for s in body["data"]["series"]} == {"web-01", "web-02"}


def test_promql_test_endpoint_reports_failure(client, admin_user, db_session, monkeypatch):
    headers = login_headers(client)
    _patch_query(monkeypatch, _fail("Grafana 认证失败"))
    resp = client.post("/api/rules/promql-test", json={"promql": "up"}, headers=headers)
    body = resp.json()
    assert body["code"] == 400
    assert "认证失败" in body["msg"]
