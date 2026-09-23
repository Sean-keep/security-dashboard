"""
Test fixtures — SQLite in-memory DB, insecure-default escape hatch, seeded admin.
"""
import os

# Must be set BEFORE app.core.config is imported: Settings validates secrets
# at construction time and refuses to build with placeholder keys.
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")
os.environ.setdefault("USE_SQLITE", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
os.environ.setdefault("SEED_SYSTEM_CONFIG", "0")
os.environ.setdefault("ENABLE_SCRIPT_EXECUTION", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.models.base import Base, get_db  # noqa: E402


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import every model so metadata is complete.
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin_user(db_session):
    from app.api.security import get_password_hash
    from app.models.user import User

    user = User(
        username="admin",
        password_hash=get_password_hash("AdminPass1"),
        nickname="Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def operator_user(db_session):
    from app.api.security import get_password_hash
    from app.models.user import User

    user = User(
        username="operator",
        password_hash=get_password_hash("OperPass1"),
        nickname="Op",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def viewer_user(db_session):
    from app.api.security import get_password_hash
    from app.models.user import User

    user = User(
        username="viewer",
        password_hash=get_password_hash("ViewPass1"),
        nickname="View",
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(engine, admin_user):
    from app.main import app

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login_headers(client, username="admin", password="AdminPass1"):
    """Log in and return an Authorization header dict (Bearer path)."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
