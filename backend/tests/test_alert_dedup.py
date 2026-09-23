"""Alert de-duplication: same source in cooldown must not spawn a new row or a new TG ping.

Before: every rule hit inserted a fresh Alert and pushed Telegram. A noisy rule
firing every minute produced hundreds of identical `pending` rows and a message
per hit. Also: `_store_raw_logs_for_alerts` wrote one 500-doc ES dump into every
alert sharing an `src_ip` inside a 1-minute window.
"""
from datetime import timedelta

from app.models.alert import Alert
from app.services.rule_executor import RuleExecutor, DEFAULT_DEDUP_COOLDOWN_SECONDS
from app.utils.timezone import local_now


def _result(ip="1.2.3.4", count=1):
    return {"src_ip": ip, "server_name": "a.example", "count": count}


def _action(rule_id=1, rule_name="r", **extra):
    return {
        "type": "create_alert",
        "severity": "medium",
        "_rule_id": rule_id,
        "_rule_name": rule_name,
        **extra,
    }


def test_repeat_hit_bumps_count_instead_of_inserting(db_session):
    ex = RuleExecutor(db_session)
    ex.process_actions([_action()], [_result(count=3)])
    ex.process_actions([_action()], [_result(count=2)])

    rows = db_session.query(Alert).all()
    assert len(rows) == 1, [r.title for r in rows]
    assert rows[0].event_count == 5
    assert rows[0].fingerprint
    assert rows[0].last_seen_at is not None


def test_different_title_is_a_different_alert(db_session):
    ex = RuleExecutor(db_session)
    ex.process_actions([_action()], [_result()])
    ex.process_actions([_action(rule_name="other")], [_result()])

    assert db_session.query(Alert).count() == 2


def test_cooldown_expiry_opens_a_new_row(db_session):
    ex = RuleExecutor(db_session)
    ex.process_actions([_action()], [_result()])
    first = db_session.query(Alert).one()
    # 模拟冷却窗口已经过去
    first.last_seen_at = local_now() - timedelta(seconds=DEFAULT_DEDUP_COOLDOWN_SECONDS + 1)
    db_session.commit()

    ex2 = RuleExecutor(db_session)
    ex2.process_actions([_action()], [_result()])
    assert db_session.query(Alert).count() == 2


def test_whitelisted_ip_is_silent(db_session):
    from app.models.address import Address

    db_session.add(Address(ip_address="9.9.9.9", status="whitelist"))
    db_session.commit()

    ex = RuleExecutor(db_session)
    ex.process_actions([_action()], [_result(ip="9.9.9.9")])
    assert db_session.query(Alert).count() == 0
    assert ex.last_alert_count == 0


def test_severity_escalates_but_never_downgrades(db_session):
    ex = RuleExecutor(db_session)
    ex.process_actions([_action(severity="critical")], [_result()])
    ex.process_actions([_action(severity="low")], [_result()])
    assert db_session.query(Alert).one().severity == "critical"

    ex2 = RuleExecutor(db_session)
    ex2.process_actions([_action(severity="low")], [_result(ip="5.5.5.5")])
    ex2.process_actions([_action(severity="high")], [_result(ip="5.5.5.5")])
    row = db_session.query(Alert).filter(Alert.src_ip == "5.5.5.5").one()
    assert row.severity == "high"


def test_telegram_only_on_transition(db_session, monkeypatch):
    """冷却窗口里的重复只抬计数，不再骚扰人。"""
    sent = []

    import app.services.telegram_notify as tn

    monkeypatch.setattr(tn, "send_telegram", lambda *a, **k: (sent.append(a), (True, ""))[1])
    monkeypatch.setattr(tn, "TELEGRAM_MAX_MESSAGES_PER_RUN", 100)

    tg = {"type": "telegram", "bot_token": "t", "chat_id": "c", "_rule_id": 1, "_rule_name": "r",
          "severity": "medium"}
    ex = RuleExecutor(db_session)
    ex.process_actions([tg], [_result()])
    assert len(sent) == 1

    ex2 = RuleExecutor(db_session)
    ex2.process_actions([tg], [_result()])
    assert len(sent) == 1, "duplicate inside cooldown must not re-push"

    # 冷却过了 → 算「又一次事件」，推
    # 先落一条告警并把它的时间拨回去
    ex3 = RuleExecutor(db_session)
    ex3.process_actions([{**tg, "type": "create_alert"}], [_result(ip="7.7.7.7")])
    row = db_session.query(Alert).filter(Alert.src_ip == "7.7.7.7").one()
    row.last_seen_at = local_now() - timedelta(seconds=DEFAULT_DEDUP_COOLDOWN_SECONDS + 5)
    db_session.commit()

    ex4 = RuleExecutor(db_session)
    ex4.process_actions([tg], [_result(ip="7.7.7.7")])
    assert len(sent) == 2


def test_create_alert_and_telegram_agree_within_one_run(db_session, monkeypatch):
    """同一规则同时配 create_alert + telegram：新告警要推，不能被自己刚建的行静音。"""
    sent = []
    import app.services.telegram_notify as tn

    monkeypatch.setattr(tn, "send_telegram", lambda *a, **k: (sent.append(a), (True, ""))[1])
    monkeypatch.setattr(tn, "TELEGRAM_MAX_MESSAGES_PER_RUN", 100)

    actions = [
        {"type": "create_alert", "severity": "medium", "_rule_id": 1, "_rule_name": "r"},
        {"type": "telegram", "bot_token": "t", "chat_id": "c", "_rule_id": 1, "_rule_name": "r",
         "severity": "medium"},
    ]
    ex = RuleExecutor(db_session)
    ex.process_actions(actions, [_result(), _result(ip="8.8.8.8")])
    assert db_session.query(Alert).count() == 2
    assert len(sent) == 2, sent


def test_created_alert_ids_are_exposed_for_raw_logs(db_session):
    ex = RuleExecutor(db_session)
    ex.process_actions([_action()], [_result(), _result(ip="2.2.2.2")])
    ex.process_actions([_action()], [_result()])  # 重复，不该进 id 列表

    assert len(ex.created_alert_ids) == 2
    rows = db_session.query(Alert).filter(Alert.id.in_(ex.created_alert_ids)).all()
    assert {r.src_ip for r in rows} == {"1.2.3.4", "2.2.2.2"}
