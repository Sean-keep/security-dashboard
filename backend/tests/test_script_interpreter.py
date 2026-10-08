"""Which interpreter runs user scripts — it must not depend on PATH.

A bare ``python3``/``pip`` resolves through the app process's PATH, so the same
build runs scripts against system packages when the service is started without
the venv activated, and ``pip install`` can land somewhere the app cannot import
from. Both are silent, so pin the resolution instead of trusting the launcher.
"""
import subprocess
import sys

from app.api import inspect as inspect_api
from app.api.inspect import _pip_cmd, _python_bin, _run_script


def test_python_bin_defaults_to_the_app_interpreter():
    """Scripts run under the same interpreter as the web app, not PATH's python3."""
    resolved = _python_bin()
    assert resolved == sys.executable
    # A bare name would be looked up on PATH at fork time. Demand an absolute
    # path so the choice cannot drift with how the service was started.
    assert resolved.startswith("/"), resolved


def test_python_bin_override_takes_precedence(monkeypatch):
    monkeypatch.setattr(inspect_api.settings, "SCRIPT_PYTHON_BIN", "/opt/other/python")
    assert _python_bin() == "/opt/other/python"


def test_python_bin_falls_back_when_sys_executable_is_empty(monkeypatch):
    """Some frozen/embedded builds leave sys.executable blank — still resolve."""
    monkeypatch.setattr(inspect_api.settings, "SCRIPT_PYTHON_BIN", "")
    monkeypatch.setattr(inspect_api.sys, "executable", "")
    assert _python_bin() == "python3"


def test_pip_cmd_is_module_pip_under_the_same_interpreter():
    cmd = _pip_cmd("install", "requests")
    assert cmd[0] == _python_bin()
    assert cmd[1:3] == ["-m", "pip"]
    assert cmd[3:] == ["install", "requests"]


def test_pip_cmd_is_not_a_path_lookup():
    """``pip`` must not be argv[0] — PATH could resolve to another interpreter.

    ``-m pip`` still names the module, which is why this checks position 0.
    """
    exe = _pip_cmd("list")[0]
    assert exe != "pip"
    assert exe.startswith("/"), exe


def test_run_script_invokes_the_resolved_interpreter(monkeypatch):
    """The call site must use _python_bin(), not a hardcoded name."""
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(inspect_api.subprocess, "run", _fake_run)
    result = _run_script("print(1)", lang="python")

    assert result["exit_code"] == 0
    assert captured["cmd"][0] == _python_bin()
    assert captured["cmd"][1:3] == ["-I", "-B"]
