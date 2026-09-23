"""Telegram 推送：凭据校验、出站脱敏、留空保持不变、失败不炸规则。"""
import json

from tests.conftest import login_headers


# ── 消息组装 ──────────────────────────────────────────────

def test_build_alert_message_includes_severity_and_ip():
    from app.services.telegram_notify import build_alert_message

    text = build_alert_message(
        title="告警: 某规则", content="检测到 1.2.3.4 攻击 a.com",
        severity="critical", src_ip="1.2.3.4", rule_name="某规则",
    )
    assert "严重" in text
    assert "1.2.3.4" in text
    assert "某规则" in text
    assert "a.com" in text


def test_build_alert_message_handles_empty_fields():
    from app.services.telegram_notify import build_alert_message

    text = build_alert_message(title="", content="")
    assert "规则告警" in text


def test_message_is_truncated_to_telegram_limit():
    from app.services import telegram_notify as tn

    ok, err = tn.send_telegram("token", "1", "x" * 9000)
    # 一定失败（假 token），但不能是因为超长被 400 拒绝 —— 我们要先截断
    assert ok is False
    assert "内容为空" not in err


# ── 凭据校验 ──────────────────────────────────────────────

def test_send_telegram_rejects_missing_credentials():
    from app.services.telegram_notify import send_telegram

    ok, err = send_telegram("", "1", "hi")
    assert ok is False and "token" in err

    ok, err = send_telegram("tok", "", "hi")
    assert ok is False and "chat_id" in err

    ok, err = send_telegram("tok", "1", "   ")
    assert ok is False and "内容" in err


def test_send_telegram_never_leaks_token_in_error(monkeypatch):
    """网络异常的报错串里不能出现 bot token。"""
    import httpx
    from app.services import telegram_notify as tn

    def _boom(*a, **kw):
        raise httpx.ConnectError("connect failed")

    monkeypatch.setattr(tn.httpx, "post", _boom)
    ok, err = tn.send_telegram("SUPER-SECRET-TOKEN", "1", "hi")
    assert ok is False
    assert "SUPER-SECRET-TOKEN" not in err
    assert "ConnectError" in err


# ── 出站脱敏 ──────────────────────────────────────────────

def _make_rule(db_session, actions):
    from app.models.rule import Rule

    rule = Rule(name="r", description="", nodes="[]", stages="[]", output_mapping="{}",
                es_index="security-logs-*", schedule_type="once", schedule_value="",
                is_enabled=True, actions=json.dumps(actions, ensure_ascii=False))
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def test_rule_api_never_returns_bot_token(client, admin_user, db_session):
    _make_rule(db_session, [
        {"type": "telegram", "bot_token": "SUPER-SECRET-TOKEN", "chat_id": "-1001"}
    ])
    headers = login_headers(client)

    listed = client.get("/api/rules", headers=headers).json()
    act = listed["data"]["list"][0]["actions"][0]
    assert "bot_token" not in act
    assert act["bot_token_set"] is True
    assert "SUPER-SECRET-TOKEN" not in json.dumps(listed)

    rule_id = listed["data"]["list"][0]["id"]
    got = client.get(f"/api/rules/{rule_id}", headers=headers).json()
    assert "SUPER-SECRET-TOKEN" not in json.dumps(got)
    assert got["data"]["actions"][0]["bot_token_set"] is True


def test_update_blank_bot_token_keeps_existing(client, admin_user, db_session):
    rule = _make_rule(db_session, [
        {"type": "telegram", "bot_token": "SUPER-SECRET-TOKEN", "chat_id": "-1001"}
    ])
    headers = login_headers(client)

    # 编辑弹窗拿不到明文，只能回送空串 —— 必须解释成「保持原值」
    resp = client.put(
        f"/api/rules/{rule.id}",
        json={"actions": [{"type": "telegram", "bot_token": "", "chat_id": "-2002"}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    from app.models.rule import Rule
    updated = client.get(f"/api/rules/{rule.id}", headers=headers).json()["data"]
    assert updated["actions"][0]["chat_id"] == "-2002"
    # token 不回传，但库里必须还在
    assert updated["actions"][0]["bot_token_set"] is True
    assert "SUPER-SECRET-TOKEN" not in json.dumps(updated)


def test_update_new_bot_token_replaces(client, admin_user, db_session):
    rule = _make_rule(db_session, [
        {"type": "telegram", "bot_token": "OLD-TOKEN", "chat_id": "-1001"}
    ])
    headers = login_headers(client)

    client.put(
        f"/api/rules/{rule.id}",
        json={"actions": [{"type": "telegram", "bot_token": "NEW-TOKEN", "chat_id": "-1001"}]},
        headers=headers,
    )
    got = client.get(f"/api/rules/{rule.id}", headers=headers).json()
    assert "NEW-TOKEN" not in json.dumps(got)
    assert got["data"]["actions"][0]["bot_token_set"] is True


# ── 执行器分发 ────────────────────────────────────────────

def test_process_actions_dispatches_telegram_and_survives_failure(db_session, monkeypatch):
    """推送失败只记日志，不能把整条 process_actions 打崩。"""
    from app.services.rule_executor import RuleExecutor

    calls = []

    def _fake_send(bot_token, chat_id, text, **kw):
        calls.append((bot_token, chat_id, text))
        return False, "模拟失败"

    monkeypatch.setattr(
        "app.services.telegram_notify.send_telegram", _fake_send, raising=True
    )

    ex = RuleExecutor(db_session)
    written = ex.process_actions(
        [{"type": "telegram", "bot_token": "T", "chat_id": "C", "_rule_name": "r"}],
        [{"src_ip": "1.2.3.4", "server_name": "a.com"}],
    )
    assert written == 0
    assert ex.last_telegram_sent == 0
    assert len(calls) == 1


def test_process_actions_telegram_caps_message_count(db_session, monkeypatch):
    from app.services.rule_executor import RuleExecutor

    calls = []

    def _fake_send(bot_token, chat_id, text, **kw):
        calls.append(text)
        return True, ""

    monkeypatch.setattr(
        "app.services.telegram_notify.send_telegram", _fake_send, raising=True
    )

    results = [{"src_ip": f"1.2.3.{i}"} for i in range(50)]
    ex = RuleExecutor(db_session)
    sent = ex.process_actions(
        [{"type": "telegram", "bot_token": "T", "chat_id": "C"}], results
    )
    assert sent == 20
    assert len(calls) == 20


def test_telegram_test_endpoint_reports_error(client, admin_user):
    headers = login_headers(client)
    resp = client.post(
        "/api/rules/telegram-test",
        json={"bot_token": "", "chat_id": ""},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "失败" in body["msg"]


def test_telegram_message_carries_rule_name(db_session, monkeypatch):
    """_rule_name 必须注入到 telegram 动作，否则推送里没有规则名。"""
    from app.services.rule_executor import RuleExecutor

    texts = []

    def _fake_send(bot_token, chat_id, text, **kw):
        texts.append(text)
        return True, ""

    monkeypatch.setattr("app.services.telegram_notify.send_telegram", _fake_send, raising=True)

    ex = RuleExecutor(db_session)
    ex.process_actions(
        [{"type": "telegram", "bot_token": "T", "chat_id": "C", "_rule_name": "高频攻击规则"}],
        [{"src_ip": "1.2.3.4"}],
    )
    assert len(texts) == 1
    assert "高频攻击规则" in texts[0]
    assert "1.2.3.4" in texts[0]
