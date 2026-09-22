"""
Application Configuration

All settings come from environment variables / `.env`. Secrets have **no**
insecure fallback: the app refuses to start with a placeholder key unless
`ALLOW_INSECURE_DEFAULTS=1` (dev/test only).
"""
from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-placeholder secrets that must never reach production.
_INSECURE_SECRETS = {
    "",
    "sec-sys-2024-safe-key",
    "jwt-sec-key-2024",
    "your-secret-key-min-32-chars",
    "your-jwt-secret-key",
    "changeme",
    "secret",
}


class Settings(BaseSettings):
    """Application settings from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Security Dashboard API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    # Dev/test only: allow placeholder secrets and short passwords.
    ALLOW_INSECURE_DEFAULTS: bool = False

    # Security
    SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 8 * 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ACCESS_COOKIE_NAME: str = "sd_access"
    REFRESH_COOKIE_NAME: str = "sd_refresh"
    COOKIE_SECURE: bool = False  # set true when serving over HTTPS
    # Comma-separated origins. Empty = same-origin only (no cross-site calls).
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost"
    # Only trust X-Real-IP / X-Forwarded-For when a reverse proxy we control
    # sits in front. Otherwise those headers are client-spoofable.
    TRUSTED_PROXY_HEADERS: bool = False

    # Password policy
    PASSWORD_MIN_LENGTH: int = 8

    # MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "security_dashboard"
    # Explicit opt-in to SQLite. MySQL is NOT silently assumed when the
    # password is empty — that hid misconfiguration in production.
    USE_SQLITE: bool = False

    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Elasticsearch
    ES_HOST: str = "localhost"
    ES_PORT: int = 9200
    ES_SCHEME: str = "https"
    ES_USER: str = ""
    ES_PASSWORD: str = ""
    ES_INDEX: str = "security-logs-*"
    ES_VERIFY_CERTS: bool = False

    # Login security
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # Script execution (inspection / blocking). Scripts run as the app user and
    # are NOT a security sandbox — see app/api/inspect.py.
    ENABLE_SCRIPT_EXECUTION: bool = True
    SCRIPT_TIMEOUT_SECONDS: int = 30
    SCRIPT_MEMORY_LIMIT_MB: int = 512

    # Unauthenticated ingest (/api/remote/ingest/{name})
    INGEST_MAX_BODY_BYTES: int = 1_048_576  # 1 MiB
    INGEST_RATE_LIMIT_PER_MINUTE: int = 120

    # Startup seeding (system config defaults). Set false to skip.
    SEED_SYSTEM_CONFIG: bool = True

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        bad = []
        if self.SECRET_KEY in _INSECURE_SECRETS:
            bad.append("SECRET_KEY")
        if self.JWT_SECRET_KEY in _INSECURE_SECRETS:
            bad.append("JWT_SECRET_KEY")
        if bad and not self.ALLOW_INSECURE_DEFAULTS:
            raise ValueError(
                f"Refusing to start: {', '.join(bad)} missing or set to a known "
                f"placeholder. Generate with `openssl rand -hex 32`, or set "
                f"ALLOW_INSECURE_DEFAULTS=1 for local development only."
            )
        if not self.USE_SQLITE and not self.MYSQL_PASSWORD and not self.ALLOW_INSECURE_DEFAULTS:
            raise ValueError(
                "Refusing to start: MYSQL_PASSWORD is empty. Set it, or set "
                "USE_SQLITE=1 for local development."
            )
        return self

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        if self.USE_SQLITE:
            import os
            sqlite_path = os.path.join(os.path.dirname(__file__), "..", "data", "security.db")
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
            return f"sqlite:///{sqlite_path}"
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def async_database_url(self) -> str:
        if self.USE_SQLITE:
            return self.database_url
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
