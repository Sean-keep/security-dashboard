"""Unauthenticated ingest must require a token and respect size/rate limits."""


def _create_endpoint(client, headers, name="src1"):
    resp = client.post(
        "/api/remote/endpoints",
        json={"name": name, "description": "test"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"], "token must be returned once at creation"
    return data


def test_create_requires_auth(client):
    client.cookies.clear()
    resp = client.post("/api/remote/endpoints", json={"name": "x"})
    assert resp.status_code == 401


def test_ingest_token_is_optional(client):
    """token 从「必须」降成「可选额外锁」—— 远程端脚本写死了不能改。

    不带 token 就收（身份靠接收端认人 + 手动绑定）；带了就必须对 ——
    用上了就不能默默放行错误密钥。
    """
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers)

    client.cookies.clear()
    # No token at all — 收。
    r1 = client.post(f"/api/remote/ingest/{ep['name']}", content=b"{}")
    assert r1.status_code == 200
    assert r1.json()["data"]["sender_status"] == "pending"
    # Wrong token — 拒。
    r2 = client.post(
        f"/api/remote/ingest/{ep['name']}",
        content=b"{}",
        headers={"X-Ingest-Token": "wrong"},
    )
    assert r2.status_code == 401
    # Correct token works.
    r3 = client.post(
        f"/api/remote/ingest/{ep['name']}",
        content=b'{"hello": 1}',
        headers={"X-Ingest-Token": ep["token"]},
    )
    assert r3.status_code == 200
    assert r3.json()["code"] == 200


def test_ingest_unknown_endpoint_is_404(client):
    client.cookies.clear()
    resp = client.post("/api/remote/ingest/nope", content=b"{}", headers={"X-Ingest-Token": "x"})
    assert resp.status_code == 404


def test_list_endpoints_never_echoes_token(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    _create_endpoint(client, headers, name="src2")
    resp = client.get("/api/remote/endpoints", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    for item in items:
        assert "token" not in item
        assert item.get("has_token") is True


def test_rotate_token_invalidates_old_token(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src3")
    old = ep["token"]

    rot = client.post(f"/api/remote/endpoints/{ep['id']}/rotate-token", headers=headers)
    assert rot.status_code == 200
    new = rot.json()["data"]["token"]
    assert new != old

    client.cookies.clear()
    stale = client.post(
        f"/api/remote/ingest/{ep['name']}",
        content=b"{}",
        headers={"X-Ingest-Token": old},
    )
    assert stale.status_code == 401

    ok = client.post(
        f"/api/remote/ingest/{ep['name']}",
        content=b"{}",
        headers={"X-Ingest-Token": new},
    )
    assert ok.status_code == 200


def test_ingest_rejects_oversized_body(client, monkeypatch):
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src4")

    import app.api.remote as remote_mod

    monkeypatch.setattr(remote_mod.settings, "INGEST_MAX_BODY_BYTES", 16)

    client.cookies.clear()
    resp = client.post(
        f"/api/remote/ingest/{ep['name']}",
        content=b"x" * 64,
        headers={"X-Ingest-Token": ep["token"]},
    )
    assert resp.status_code == 413


def test_ingest_rate_limited(client, monkeypatch):
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src5")

    import app.api.remote as remote_mod

    monkeypatch.setattr(remote_mod.settings, "INGEST_RATE_LIMIT_PER_MINUTE", 3)
    remote_mod._INGEST_HITS.clear()

    client.cookies.clear()
    statuses = []
    for _ in range(5):
        r = client.post(
            f"/api/remote/ingest/{ep['name']}",
            content=b"{}",
            headers={"X-Ingest-Token": ep["token"]},
        )
        statuses.append(r.status_code)
    assert statuses.count(200) == 3
    assert 429 in statuses


def test_endpoint_name_validated(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    resp = client.post(
        "/api/remote/endpoints",
        json={"name": "../etc/passwd"},
        headers=headers,
    )
    # Pydantic rejects the name pattern -> FastAPI returns 422.
    assert resp.status_code == 422


# ── 幂等与源端时序 ────────────────────────────────────────────

def test_message_id_is_idempotent(client):
    """推送端遇到 429/5xx 必然重投 —— 同一个 X-Message-Id 不能变成两行。"""
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src6")
    client.cookies.clear()
    hdr = {"X-Ingest-Token": ep["token"], "X-Message-Id": "evt-1"}

    first = client.post(f"/api/remote/ingest/{ep['name']}", content=b'{"n":1}', headers=hdr)
    assert first.status_code == 200
    assert first.json()["data"]["duplicate"] is False
    fid = first.json()["data"]["id"]

    second = client.post(f"/api/remote/ingest/{ep['name']}", content=b'{"n":1}', headers=hdr)
    assert second.status_code == 200
    assert second.json()["data"]["duplicate"] is True
    assert second.json()["data"]["id"] == fid

    listed = client.get(f"/api/remote/endpoints/{ep['id']}/logs", headers=login_headers(client))
    assert listed.json()["data"]["total"] == 1


def test_sent_at_is_stored_and_orders_listing(client):
    """重试送达的旧批次不能顶掉新数据 —— 列表必须按源端发送时间排。"""
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src7")
    client.cookies.clear()
    tok = {"X-Ingest-Token": ep["token"]}

    # 先投「新」的，再投一条迟到的「旧」的
    client.post(f"/api/remote/ingest/{ep['name']}", content=b'{"new":1}',
                headers={**tok, "X-Message-Id": "b", "X-Sent-At": "2026-09-23T12:00:00"})
    client.post(f"/api/remote/ingest/{ep['name']}", content=b'{"old":1}',
                headers={**tok, "X-Message-Id": "a", "X-Sent-At": "2026-09-23T09:00:00"})

    listed = client.get(f"/api/remote/endpoints/{ep['id']}/logs", headers=login_headers(client))
    items = listed.json()["data"]["items"]
    assert items[0]["message_id"] == "b", items
    assert items[0]["sent_at"] == "2026-09-23 12:00:00"


def test_last_received_at_is_stamped(client):
    """存活信号：没有它分不清「agent 挂了」和「本来就没数据」。"""
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers, name="src8")

    before = client.get("/api/remote/endpoints", headers=headers).json()["data"]
    assert all(i["seconds_since_last"] is None for i in before if i["name"] == "src8")

    client.cookies.clear()
    client.post(f"/api/remote/ingest/{ep['name']}", content=b'{}',
                headers={"X-Ingest-Token": ep["token"]})

    after = client.get("/api/remote/endpoints", headers=login_headers(client)).json()["data"]
    row = next(i for i in after if i["name"] == "src8")
    assert row["last_received_at"]
    assert row["seconds_since_last"] is not None


# ── 铸造/轮换凭据必须是 admin ────────────────────────────────

def test_non_admin_cannot_mint_or_rotate_token(client, operator_user):
    """轮换会让正当源立刻断供、创建等于开一条无鉴权写库通道 —— 不能只要登录就行。"""
    from tests.conftest import login_headers

    admin_h = login_headers(client)
    ep = _create_endpoint(client, admin_h, name="src9")

    op_h = login_headers(client, "operator", "OperPass1")
    assert client.post("/api/remote/endpoints", json={"name": "src9b"}, headers=op_h).status_code == 403
    assert client.post(f"/api/remote/endpoints/{ep['id']}/rotate-token", headers=op_h).status_code == 403
    assert client.put(f"/api/remote/endpoints/{ep['id']}", json={"description": "x"}, headers=op_h).status_code == 403
    assert client.delete(f"/api/remote/endpoints/{ep['id']}", headers=op_h).status_code == 403
    assert client.delete(f"/api/remote/endpoints/{ep['id']}/logs", headers=op_h).status_code == 403
