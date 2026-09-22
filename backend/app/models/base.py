"""
Database Base and Session Management
SQLAlchemy 2.0 style

Timestamps are naive **local** time (container TZ = Asia/Shanghai); MySQL
sessions set ``time_zone='+08:00'`` so driver and column values agree. JWT
uses UTC separately — see app/utils/timezone.py.
"""
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, DateTime, Text, create_engine
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.utils.timezone import local_now


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


# Large text payloads (raw ES log batches, full inspection reports).
# MySQL gets MEDIUMTEXT (~16MB); SQLite — used by USE_SQLITE=1 for dev/test —
# gets plain TEXT, which is unbounded in practice. Keeps create_all portable.
LongText = Text().with_variant(MEDIUMTEXT(), "mysql")


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now, nullable=False)


_db_url = settings.database_url
_engine_kwargs = {
    'echo': settings.DEBUG,
    'pool_pre_ping': True,
    'pool_recycle': 3600,
    'pool_size': settings.DB_POOL_SIZE,
    'max_overflow': settings.DB_MAX_OVERFLOW,
}
if _db_url.startswith('mysql'):
    # PyMySQL 1.2+ no longer accepts serverTimezone in URL; use connect_args instead
    _engine_kwargs['connect_args'] = {
        'init_command': "SET time_zone='+08:00', NAMES utf8mb4",
        'charset': 'utf8mb4',
    }
elif _db_url.startswith('sqlite'):
    # SQLite is single-writer; drop pool knobs it does not understand.
    _engine_kwargs.pop('pool_pre_ping', None)
    _engine_kwargs.pop('pool_recycle', None)
    _engine_kwargs.pop('pool_size', None)
    _engine_kwargs.pop('max_overflow', None)
    _engine_kwargs['connect_args'] = {'check_same_thread': False}

engine = create_engine(_db_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database (create tables)

    NOTE: create_all only bootstraps. Schema changes on live data need a
    migration script — see docs/ and scripts/.
    """
    Base.metadata.create_all(bind=engine)
