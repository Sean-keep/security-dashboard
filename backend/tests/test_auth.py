"""Auth: login lockout, password policy, token type claims, cookie delivery."""
from datetime import timedelta

import pytest

from app.api.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from app.core.policy import validate_password_strength
from app.models.user import LoginLog
from app.utils.timezone import local_now


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["short", "12345678", "alllowercase", "ALLUPPERCASE", "password"])
def test_password_policy_rejects_weak(bad):
    with pytest.raises(ValueError):
        validate_password_strength(bad)


def test_password_policy_accepts_good():
    validate_password_strength("OperPass1")


def test_password_hash_roundtrip():
    h = get_password_hash("OperPass1")
    assert verify_password("OperPass1", h)
    assert not verify_password("WrongPass1", h)


# ---------------------------------------------------------------------------
# JWT type claims
# ---------------------------------------------------------------------------

def test_access_and_refresh_tokens_are_not_interchangeable(admin_user):
    access = create_access_token({"sub": str(admin_user.id)})
    refresh = create_refresh_token(admin_user.id)

    assert decode_access_token(access) == admin_user.id
    assert decode_refresh_token(refresh) == admin_user.id

    # Cross-use must fail.
    assert decode_access_token(refresh) is None
    assert decode_refresh_token(access) is None


def test_garbage_token_returns_none():
    assert decode_access_token("not-a-jwt") is None
    assert decode_access_token("") is None


# ---------------------------------------------------------------------------
# Login + lockout
# ---------------------------------------------------------------------------

def test_login_success_sets_cookies_and_tokens(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["user"]["role"] == "admin"
    # HttpOnly cookies must be present so the SPA can authenticate without localStorage.
    assert "sd_access" in resp.cookies
    assert "sd_refresh" in resp.cookies


def test_login_wrong_password_is_generic(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401
    # Must not reveal whether the username exists.
    assert "用户名或密码错误" in resp.text


def test_login_unknown_user_is_generic(client):
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert resp.status_code == 401
    assert "用户名或密码错误" in resp.text


def test_lockout_after_repeated_failures(client, db_session):
    # Fill the failure streak (default max_attempts = 5).
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    assert resp.status_code == 429


def test_success_resets_lockout_streak(client, db_session):
    for _ in range(3):
        client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    # A success must break the streak.
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    assert ok.status_code == 200
    for _ in range(3):
        client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    # 3 failures after a success is still under the limit of 5.
    still_ok = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    assert still_ok.status_code == 200


def test_x_forwarded_for_is_ignored_by_default(client, db_session):
    """Without TRUSTED_PROXY_HEADERS the XFF header must not dodge lockout."""
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "bad"},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass1"},
        headers={"X-Forwarded-For": "198.51.100.99"},  # fresh "IP"
    )
    assert resp.status_code == 429


class _FakeRequest:
    """Minimal stand-in for starlette Request in get_client_ip unit tests."""

    def __init__(self, headers=None, client_host="10.0.0.5"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})()


def test_client_ip_prefers_real_ip_over_xff(monkeypatch):
    from app.api import auth as auth_mod

    monkeypatch.setattr(auth_mod.settings, "TRUSTED_PROXY_HEADERS", True)
    req = _FakeRequest({"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert auth_mod.get_client_ip(req) == "203.0.113.7"


def test_client_ip_takes_rightmost_xff_hop(monkeypatch):
    """Left-most hop is client-controlled even through $proxy_add_x_forwarded_for."""
    from app.api import auth as auth_mod

    monkeypatch.setattr(auth_mod.settings, "TRUSTED_PROXY_HEADERS", True)
    req = _FakeRequest({"X-Forwarded-For": "spoofed.attacker, 203.0.113.7"})
    assert auth_mod.get_client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_socket_peer(monkeypatch):
    from app.api import auth as auth_mod

    monkeypatch.setattr(auth_mod.settings, "TRUSTED_PROXY_HEADERS", False)
    req = _FakeRequest({"X-Real-IP": "203.0.113.7"}, client_host="10.0.0.5")
    assert auth_mod.get_client_ip(req) == "10.0.0.5"


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

def test_me_accepts_cookie_only(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    token = login.json()["data"]["token"]
    # TestClient persists cookies from the login response automatically.
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"
    # And also works via Bearer.
    resp2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200


def test_me_without_credentials_is_401(client):
    client.cookies.clear()
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_refresh_rotates_tokens(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    old_access = login.json()["data"]["token"]
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    new_access = resp.json()["data"]["token"]
    assert new_access and new_access != old_access
    # The refreshed access token must actually work.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


def test_logout_clears_session(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200


def test_change_password_enforces_policy(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass1"})
    weak = client.post(
        "/api/auth/change-password",
        json={"old_password": "AdminPass1", "new_password": "weak"},
    )
    assert weak.status_code == 400
    # The message must be the specific Chinese policy error, not a bare 422.
    assert "密码" in weak.text or "长度" in weak.text

    same = client.post(
        "/api/auth/change-password",
        json={"old_password": "AdminPass1", "new_password": "AdminPass1"},
    )
    assert same.status_code == 400

    ok = client.post(
        "/api/auth/change-password",
        json={"old_password": "AdminPass1", "new_password": "NewAdmin1"},
    )
    assert ok.status_code == 200
