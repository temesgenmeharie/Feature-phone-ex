"""Audit trail query endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.models.forensics import AuditLog, Examiner
from app.schemas import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    case_id: int | None = Query(default=None),
    acquisition_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> list[AuditLogOut]:
    query = db.query(AuditLog)
    if case_id is not None:
        query = query.filter(AuditLog.case_id == case_id)
    if acquisition_id is not None:
        query = query.filter(AuditLog.acquisition_id == acquisition_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    entries = query.order_by(AuditLog.id.desc()).limit(limit).all()
    return [AuditLogOut.model_validate(e) for e in entries]

