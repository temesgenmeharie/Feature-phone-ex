"""Shared Pytest fixtures for backend tests."""

from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.forensics import Examiner, ExaminerRole


@pytest.fixture()
def test_db(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_forensics.db"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "evidence_dir", evidence_dir)

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

    yield TestingSessionLocal, evidence_dir
