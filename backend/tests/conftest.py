"""Shared Pytest fixtures for backend tests."""

import asyncio
from pathlib import Path
import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.forensics import Examiner, ExaminerRole


class SyncASGIClient:
    """Synchronous wrapper around httpx.AsyncClient + ASGITransport (avoids Starlette portal hangs)."""

    def __init__(self, app) -> None:
        self._app = app

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def _send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                return await ac.request(method, url, **kwargs)

        return asyncio.run(_send())

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)


@pytest.fixture()
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_forensics.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        admin = Examiner(
            username="admin",
            full_name="Test Admin",
            email="admin@test.local",
            role=ExaminerRole.ADMIN,
            password_hash=hash_password("AdminPass123!"),
            is_active=True,
        )
        examiner = Examiner(
            username="examiner1",
            full_name="Test Examiner",
            email="examiner1@test.local",
            role=ExaminerRole.EXAMINER,
            password_hash=hash_password("ExaminerPass123!"),
            is_active=True,
        )
        db.add_all([admin, examiner])
        db.commit()

    yield TestingSessionLocal, tmp_path / "evidence"


@pytest.fixture()
def client(test_db, monkeypatch):
    TestingSessionLocal, evidence_dir = test_db
    evidence_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "evidence_dir", evidence_dir)
    monkeypatch.setattr("app.main.init_db", lambda: None)

    app = create_app()

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return SyncASGIClient(app)
