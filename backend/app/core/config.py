"""
Application Configuration
支持环境变量和数据库动态配置
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Application
    APP_NAME: str = "Security Dashboard API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    
    # Security
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "sec-sys-2024-safe-key")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "jwt-sec-key-2024")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    
    # MySQL (default, can be overridden by database config)
    MYSQL_HOST: str = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.environ.get("MYSQL_DATABASE", "security_dashboard")
    
    # SQLite fallback (when USE_SQLITE=1 or no MySQL password)
    USE_SQLITE: bool = os.environ.get("USE_SQLITE", "0") == "1" or not os.environ.get("MYSQL_PASSWORD")
    
    # Elasticsearch
    ES_HOST: str = os.environ.get("ES_HOST", "localhost")
    ES_PORT: int = int(os.environ.get("ES_PORT", "9200"))
    ES_SCHEME: str = os.environ.get("ES_SCHEME", "https")
    ES_USER: str = os.environ.get("ES_USER", "")
    ES_PASSWORD: str = os.environ.get("ES_PASSWORD", "")
    ES_INDEX: str = os.environ.get("ES_INDEX", "security-logs-*")
    ES_VERIFY_CERTS: bool = os.environ.get("ES_VERIFY_CERTS", "false").lower() == "true"
    
    # Login security
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    LOGIN_RETRY_INTERVAL_SECONDS: int = 60
    
    @property
    def database_url(self) -> str:
        """Get database URL based on configuration"""
        if self.USE_SQLITE:
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
        """Get async database URL"""
        if self.USE_SQLITE:
            # SQLite doesn't support async in the same way, fallback to sync
            return self.database_url
        
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
