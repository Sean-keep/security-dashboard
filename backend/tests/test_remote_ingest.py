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


def test_ingest_requires_token(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    ep = _create_endpoint(client, headers)

    client.cookies.clear()
    # No token at all.
    r1 = client.post(f"/api/remote/ingest/{ep['name']}", content=b"{}")
    assert r1.status_code == 401
    # Wrong token.
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
