"""Database engine, session factory, and initialization."""

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
  

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables, ensure evidence directory exists, and seed default lab admin."""
    from app.models.forensics import Examiner, ExaminerRole  # noqa: F401

    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        existing_admin = db.query(Examiner).filter(Examiner.username == settings.default_admin_username).first()
        if not existing_admin:
            admin = Examiner(
                username=settings.default_admin_username,
                full_name=settings.default_admin_full_name,
                email="admin@forensics.local",
                role=ExaminerRole.ADMIN,
                password_hash=hash_password(settings.default_admin_password),
                is_active=True,
            )
            db.add(admin)
            db.commit()

