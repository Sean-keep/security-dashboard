"""
Database Base and Session Management
SQLAlchemy 2.0 style
"""
from datetime import datetime
from typing import Generator
from sqlalchemy import create_engine, Column, DateTime
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


import urllib.parse as _urllib_parse

_db_url = settings.database_url
_engine_kwargs = {
    'echo': settings.DEBUG,
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}
if _db_url.startswith('mysql'):
    # PyMySQL 1.2+ no longer accepts serverTimezone in URL; use connect_args instead
    _engine_kwargs['connect_args'] = {'init_command': "SET time_zone='+08:00'"}

# Create engine
engine = create_engine(
    _db_url,
    **_engine_kwargs,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database (create tables)"""
    Base.metadata.create_all(bind=engine)
