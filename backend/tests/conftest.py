import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db, get_session_factory
from app.main import app
from app.rate_limit import _hits as _ai_rate_limit_hits


@pytest.fixture(autouse=True)
def _clear_ai_rate_limit_buckets():
    # Module-global and keyed by user id, which restarts at 1 in every test's
    # fresh SQLite DB - without resetting it, hits accumulate across unrelated
    # tests/files in the same run and can spuriously rate-limit a later test.
    _ai_rate_limit_hits.clear()
    yield
    _ai_rate_limit_hits.clear()


@pytest.fixture(autouse=True)
def _enable_live_question_generation(monkeypatch):
    # Off by default in production (generation only happens explicitly from the
    # Question Bank tab), but most existing session tests exercise the on-the-fly
    # generation fallback directly, so it's on by default here. Tests covering
    # the disabled gating override it back to False explicitly.
    monkeypatch.setattr(settings, "live_question_generation_enabled", True)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: TestingSessionLocal

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_user(client):
    def _make_user(email: str, password: str = "password123") -> dict[str, str]:
        client.post("/auth/register", json={"email": email, "password": password})
        login = client.post("/auth/login", json={"email": email, "password": password})
        token = login.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make_user
