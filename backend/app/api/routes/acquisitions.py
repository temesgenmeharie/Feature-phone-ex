"""Acquisition execution, logs, evidence listing, and SHA-256 verification endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.extraction.interfaces import ExtractionCategory
from app.extraction.orchestrator import ExtractionOrchestrator
from app.models.forensics import (
    ATCommandLog,
    Acquisition,
    AcquisitionStatus,
    Case,
    Device,
    EvidenceFile,
    Examiner,
)
from app.preservation.vault import verify_acquisition_evidence
from app.serial.manager import session_manager
from app.serial.transport import SerialTransportError

router = APIRouter(prefix="/acquisitions", tags=["acquisitions"])


class AcquisitionCreate(BaseModel):
    case_id: int
    device_id: int
    categories: list[ExtractionCategory] = Field(min_length=1)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    status: str
    records_extracted: int
    details: str | None


class AcquisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    acquisition_uid: str
    case_id: int
    device_id: int
    examiner_id: int
    extraction_method: str
    status: AcquisitionStatus
    evidence_dir: str
    started_at: datetime
    completed_at: datetime | None
    limitations_json: list[str] | None
    tasks: list[TaskOut] = []


class ATLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    command: str
    response: str
    terminal_status: str
    duration_ms: int
    executed_at: datetime


class EvidenceFileOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: str
    file_size_bytes: int
    is_immutable: bool
    sha256: str | None
    last_verified_at: datetime | None
    last_verification_passed: bool | None


@router.post("", response_model=AcquisitionOut, status_code=status.HTTP_201_CREATED)
def start_acquisition(
    payload: AcquisitionCreate,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> AcquisitionOut:
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    device = db.query(Device).filter(Device.id == payload.device_id, Device.case_id == case.id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found for case")

    try:
        engine = session_manager.require_engine()
    except SerialTransportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    acq, _ = ExtractionOrchestrator().run_acquisition(
        db,
        engine,
        case_id=case.id,
        device=device,
        examiner=current_examiner,
        categories=payload.categories,
    )
    return AcquisitionOut.model_validate(acq)


@router.get("", response_model=list[AcquisitionOut])
def list_acquisitions(
    case_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> list[AcquisitionOut]:
    q = db.query(Acquisition)
    if case_id is not None:
        q = q.filter(Acquisition.case_id == case_id)
    acqs = q.order_by(Acquisition.id.desc()).all()
    return [AcquisitionOut.model_validate(a) for a in acqs]


@router.get("/{acquisition_id}", response_model=AcquisitionOut)
def get_acquisition(
    acquisition_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> AcquisitionOut:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    return AcquisitionOut.model_validate(acq)


@router.get("/{acquisition_id}/logs", response_model=list[ATLogOut])
def get_acquisition_logs(
    acquisition_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> list[ATLogOut]:
    logs = (
        db.query(ATCommandLog)
        .filter(ATCommandLog.acquisition_id == acquisition_id)
        .order_by(ATCommandLog.id.asc())
        .all()
    )
    return [ATLogOut.model_validate(l) for l in logs]


@router.get("/{acquisition_id}/evidence", response_model=list[EvidenceFileOut])
def list_acquisition_evidence(
    acquisition_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> list[EvidenceFileOut]:
    files = db.query(EvidenceFile).filter(EvidenceFile.acquisition_id == acquisition_id).all()
    return [
        EvidenceFileOut(
            id=f.id,
            file_name=f.file_name,
            file_path=f.file_path,
            file_type=f.file_type.value,
            file_size_bytes=f.file_size_bytes,
            is_immutable=f.is_immutable,
            sha256=f.evidence_hash.digest_hex if f.evidence_hash else None,
            last_verified_at=f.evidence_hash.last_verified_at if f.evidence_hash else None,
            last_verification_passed=f.evidence_hash.last_verification_passed if f.evidence_hash else None,
        )
        for f in files
    ]


@router.post("/{acquisition_id}/verify")
def verify_evidence(
    acquisition_id: int,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> dict[str, Any]:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    return verify_acquisition_evidence(db, acquisition_id, current_examiner)

