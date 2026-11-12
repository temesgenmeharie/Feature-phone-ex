"""Immutable audit logging service."""

from typing import Any
from sqlalchemy.orm import Session

from app.models.forensics import AuditLog


def record_audit_event(
    db: Session,
    action: str,
    *,
    examiner_id: int | None = None,
    case_id: int | None = None,
    acquisition_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit log entry to the database."""
    entry = AuditLog(
        examiner_id=examiner_id,
        case_id=case_id,
        acquisition_id=acquisition_id,
        action=action,
        details_json=details,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

