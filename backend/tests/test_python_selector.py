"""The Python interpreter selector — discovery, validation, and config plumbing.

Two things are being pinned down here:

1. A custom path must prove it is actually Python (and an absolute path) before
   it can be saved. Accepting a bare name would reintroduce the PATH drift this
   whole mechanism exists to remove.
2. The key must be savable on a DB where the startup seed never ran — the test
   suite runs with ``SEED_SYSTEM_CONFIG=0``, and ``save_config`` hard-rejects
   keys with no SystemConfig row.
"""
import os
import sys

import pytest

from app.api.inspect import _probe_python, _resolve_python_bin, _python_source
from app.models.config import SystemConfig


# ---------------------------------------------------------------------------
# _probe_python — the validator both endpoints share
# ---------------------------------------------------------------------------

def test_probe_accepts_the_app_interpreter():
    info = _probe_python(sys.executable)
    assert info["ok"], info["error"]
    assert info["version"]  # e.g. "3.12.3"
    assert info["has_pip"] is True
    assert info["realpath"]


def test_probe_rejects_empty_and_relative_paths():
    assert _probe_python("")["ok"] is False
    assert _probe_python("   ")["ok"] is False
    rel = _probe_python("python3")
    assert rel["ok"] is False
    assert "绝对路径" in rel["error"]


def test_probe_rejects_missing_file():
    info = _probe_python("/nonexistent/python-bin")
    assert info["ok"] is False
    assert "不存在" in info["error"]


def test_probe_rejects_non_python_executable():
    if not os.path.isfile("/bin/true"):
        pytest.skip("/bin/true not present")
    info = _probe_python("/bin/true")
    assert info["ok"] is False, "/bin/true must not pass as a Python interpreter"
    assert info["error"]


def test_probe_rejects_unexecutable_file(tmp_path):
    p = tmp_path / "python"
    p.write_text("#!/bin/sh\necho hi\n")
    p.chmod(0o644)
    info = _probe_python(str(p))
    assert info["ok"] is False
    assert "不可执行" in info["error"]


def test_probe_refuses_nul_byte():
    assert _probe_python("/bin/te\x00st")["ok"] is False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def test_interpreters_require_authentication(client):
    client.cookies.clear()
    assert client.get("/api/inspect/python-interpreters").status_code in (401, 403)
    assert client.post("/api/inspect/python-interpreters/test", json={"path": "/x"}).status_code in (401, 403)
    assert client.get("/api/inspect/python-interpreters/effective").status_code in (401, 403)


def test_discovery_is_admin_only(client, operator_user):
    from tests.conftest import login_headers

    headers = login_headers(client, username="operator", password="OperPass1")
    assert client.get("/api/inspect/python-interpreters", headers=headers).status_code == 403
    # ...but operators must still see the read-only hint on the scripts page.
    assert client.get("/api/inspect/python-interpreters/effective", headers=headers).status_code == 200


def test_discovery_lists_the_app_interpreter(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    resp = client.get("/api/inspect/python-interpreters", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]

    assert body["effective"]["source"] in ("env", "db", "default")
    assert "locked" in body["effective"]

    # Key on (realpath, is_venv) — realpath alone merges a venv with its base.
    wanted = (os.path.realpath(sys.executable), sys.prefix != sys.base_prefix)
    by_id = {(os.path.realpath(i["path"]), bool(i.get("is_venv"))): i for i in body["items"]}
    me = by_id.get(wanted)
    assert me is not None, f"sys.executable must be among the candidates: {sorted(by_id)}"
    assert me["ok"] is True
    assert me["is_current"] is True


def test_venv_and_its_base_interpreter_are_both_listed(client):
    """A venv's python is a symlink to the system one — realpath alone collapses them.

    They have different site-packages, so the system interpreter must survive
    dedupe. Regression: it used to vanish behind the venv symlink target, and
    ``is_current`` was true for both rows.
    """
    from tests.conftest import login_headers

    headers = login_headers(client)
    items = client.get("/api/inspect/python-interpreters", headers=headers).json()["data"]["items"]

    current = [i for i in items if i["is_current"]]
    assert len(current) == 1, f"exactly one row may claim to be current, got {current}"

    # Only meaningful when the app actually runs in a venv whose python symlinks
    # to a shared base — which is the normal case here.
    base = getattr(sys, "base_prefix", sys.prefix)
    base_python = os.path.join(base, "bin", "python3")
    if sys.prefix == sys.base_prefix or not os.path.realpath(sys.executable) == os.path.realpath(base_python):
        pytest.skip("app interpreter is not a venv symlink to its base")

    assert any(bool(i.get("is_venv")) for i in items), "the venv interpreter should be listed"
    assert any(not i.get("is_venv") and i["ok"] for i in items), "the base interpreter must not be deduped away"


def test_discovery_skips_non_interpreter_neighbors():
    """python3-config etc. are not interpreters and should never be candidates."""
    from app.api.inspect import _interpreter_candidates

    names = {os.path.basename(p) for p in _interpreter_candidates()}
    assert not any(n.endswith("-config") or n.endswith("-dbg") for n in names), names


def test_test_endpoint_validates_custom_path(client):
    from tests.conftest import login_headers

    headers = login_headers(client)
    ok = client.post("/api/inspect/python-interpreters/test",
                     json={"path": sys.executable}, headers=headers)
    assert ok.status_code == 200 and ok.json()["data"]["ok"] is True

    bad = client.post("/api/inspect/python-interpreters/test",
                      json={"path": "python3"}, headers=headers)
    assert bad.status_code == 200 and bad.json()["data"]["ok"] is False


def test_test_endpoint_respects_kill_switch(client, monkeypatch):
    from tests.conftest import login_headers
    from app.api import inspect as inspect_api

    monkeypatch.setattr(inspect_api.settings, "ENABLE_SCRIPT_EXECUTION", False)
    headers = login_headers(client)
    resp = client.post("/api/inspect/python-interpreters/test",
                       json={"path": sys.executable}, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Config plumbing — the key must be savable without the startup seed
# ---------------------------------------------------------------------------

def test_save_config_accepts_script_python_bin_without_startup_seed(client):
    """conftest sets SEED_SYSTEM_CONFIG=0, so this proves the call-time seed."""
    from tests.conftest import login_headers

    headers = login_headers(client)
    # GET /config triggers the ensure, same as the real settings page does.
    client.get("/api/settings/config", headers=headers)
    resp = client.put("/api/settings/config",
                      json={"updates": {"script_python_bin": sys.executable}},
                      headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 200


def test_script_python_bin_round_trips_unmasked(client, db_session):
    """Not a secret key — the form must read the value back, not ''."""
    from tests.conftest import login_headers

    headers = login_headers(client)
    client.put("/api/settings/config",
               json={"updates": {"script_python_bin": sys.executable}}, headers=headers)

    groups = client.get("/api/settings/config", headers=headers).json()["data"]
    rows = [r for g in groups.values() for r in g if r["key"] == "script_python_bin"]
    assert rows, "script_python_bin missing from GET /config"
    assert rows[0]["value"] == sys.executable
    assert rows[0].get("secret_set") in (None, False)
    assert rows[0]["group_name"] == "script"


# ---------------------------------------------------------------------------
# Resolution precedence
# ---------------------------------------------------------------------------

def test_db_value_beats_the_default(db_session):
    db_session.add(SystemConfig(key="script_python_bin", value="/opt/custom/python"))
    db_session.commit()
    assert _resolve_python_bin(db_session) == "/opt/custom/python"
    assert _python_source(db_session) == "db"


def test_empty_db_value_falls_through_to_app_interpreter(db_session):
    db_session.add(SystemConfig(key="script_python_bin", value="   "))
    db_session.commit()
    assert _resolve_python_bin(db_session) == sys.executable
    assert _python_source(db_session) == "default"


def test_env_pin_beats_db(db_session, monkeypatch):
    from app.api import inspect as inspect_api

    db_session.add(SystemConfig(key="script_python_bin", value="/from/db"))
    db_session.commit()
    monkeypatch.setattr(inspect_api.settings, "SCRIPT_PYTHON_BIN", "/from/env")

    assert _resolve_python_bin(db_session) == "/from/env"
    assert _python_source(db_session) == "env"


def test_without_db_session_still_resolves():
    """Callers with no session (and the frozen-binary path) keep working."""
    assert _resolve_python_bin(None) == sys.executable
    assert _python_source(None) == "default"


def test_broken_configured_interpreter_fails_loud(db_session, monkeypatch):
    """Never silently substitute another interpreter — that is the bug we fixed."""
    from app.api.inspect import _run_script

    db_session.add(SystemConfig(key="script_python_bin", value="/nope/gone-python"))
    db_session.commit()

    result = _run_script("print(1)", lang="python", db=db_session)
    assert result["exit_code"] == 1
    assert "/nope/gone-python" in result["stderr"]
    assert "print(1)" not in result["stdout"]
