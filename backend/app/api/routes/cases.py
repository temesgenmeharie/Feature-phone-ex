"""Forensic examination case management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner, require_admin
from app.db.session import get_db
from app.models.forensics import Case, CaseStatus, Examiner
from app.schemas import CaseCreate, CaseOut, CaseUpdate
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> CaseOut:
    if db.query(Case).filter(Case.case_number == payload.case_number).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case number already exists")

    case = Case(
        case_number=payload.case_number,
        title=payload.title,
        purpose=payload.purpose,
        device_owner_ref=payload.device_owner_ref,
        device_description=payload.device_description,
        notes=payload.notes,
        lead_examiner_id=current_examiner.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    record_audit_event(
        db,
        "CASE_CREATED",
        examiner_id=current_examiner.id,
        case_id=case.id,
        details={"case_number": case.case_number},
    )
    return CaseOut.model_validate(case)


@router.get("", response_model=list[CaseOut])
def list_cases(
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> list[CaseOut]:
    query = db.query(Case)
    if status_filter is not None:
        query = query.filter(Case.status == status_filter)
    if search:
        pattern = f"%{search}%"
        query = query.filter((Case.case_number.ilike(pattern)) | (Case.title.ilike(pattern)))
    cases = query.order_by(Case.created_at.desc()).all()
    return [CaseOut.model_validate(c) for c in cases]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> CaseOut:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return CaseOut.model_validate(case)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> CaseOut:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    record_audit_event(
        db,
        "CASE_UPDATED",
        examiner_id=current_examiner.id,
        case_id=case.id,
        details={"updated_fields": list(updates.keys())},
    )
    return CaseOut.model_validate(case)


@router.post("/purge-all", status_code=status.HTTP_200_OK)
def purge_all_records(
    db: Session = Depends(get_db),
    admin: Examiner = Depends(require_admin),
) -> dict[str, str]:
    """Admin-only: purge all cases, acquisitions, and extracted records."""
    from app.models.forensics import (
        Acquisition,
        ATCommandLog,
        CallRecord,
        Contact,
        Device,
        EvidenceFile,
        EvidenceHash,
        ExtractionTask,
        SmsMessage,
    )
    for model in (
        EvidenceHash,
        EvidenceFile,
        Contact,
        SmsMessage,
        CallRecord,
        ExtractionTask,
        ATCommandLog,
        Acquisition,
        Device,
        Case,
    ):
        db.query(model).delete()
    db.commit()
    record_audit_event(
        db,
        "PURGE_ALL_RECORDS",
        examiner_id=admin.id,
        details={"action": "All cases, acquisitions, and extracted evidence purged."},
    )
    return {"message": "All examination cases, devices, acquisitions, and extracted records have been cleared."}
