"""Startup configuration: secrets must not silently fall back to placeholders."""
import importlib

import pytest


def _reload_settings(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.core.config as config_mod

    config_mod.get_settings.cache_clear()
    try:
        return importlib.reload(config_mod)
    finally:
        config_mod.get_settings.cache_clear()


def test_rejects_placeholder_secret_key(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULTS", "0")
    monkeypatch.setenv("SECRET_KEY", "sec-sys-2024-safe-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("USE_SQLITE", "1")
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ValueError)):
        _reload_settings(monkeypatch)


def test_rejects_empty_mysql_password_without_sqlite(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULTS", "0")
    monkeypatch.setenv("SECRET_KEY", "b" * 32)
    monkeypatch.setenv("JWT_SECRET_KEY", "c" * 32)
    monkeypatch.setenv("MYSQL_PASSWORD", "")
    monkeypatch.setenv("USE_SQLITE", "0")

    with pytest.raises((ValueError, Exception)):
        _reload_settings(monkeypatch)


def test_accepts_real_secrets(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULTS", "0")
    monkeypatch.setenv("SECRET_KEY", "d" * 32)
    monkeypatch.setenv("JWT_SECRET_KEY", "e" * 32)
    monkeypatch.setenv("USE_SQLITE", "1")

    mod = _reload_settings(monkeypatch)
    assert mod.settings.SECRET_KEY == "d" * 32
    assert mod.settings.USE_SQLITE is True


def test_allowed_origins_parsed():
    from app.core.config import settings

    assert isinstance(settings.allowed_origins, list)
