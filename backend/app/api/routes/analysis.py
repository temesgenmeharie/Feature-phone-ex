"""Forensic data analysis and dashboard summary endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.models.forensics import (
    Acquisition,
    AcquisitionStatus,
    AuditLog,
    CallRecord,
    CallType,
    Case,
    Contact,
    Device,
    Examiner,
    ExtractionTask,
    SmsMessage,
    TaskCategory,
)
from app.serial.manager import session_manager

router = APIRouter(tags=["analysis"])


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_index: int | None
    name: str | None
    phone_number: str
    number_type: str | None
    storage_location: str


class SmsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_index: int | None
    status: str | None
    sender_or_recipient: str | None
    timestamp_raw: str | None
    timestamp_iso: datetime | None
    content: str | None
    storage_location: str
    pdu_hex: str | None


class CallRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_type: CallType
    record_index: int | None
    phone_number: str
    contact_name: str | None
    timestamp_raw: str | None
    timestamp_iso: datetime | None
    duration_seconds: int | None
    storage_location: str
    is_cdr_level: bool


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> dict[str, Any]:
    total_cases = db.query(Case).count()
    completed_acq = (
        db.query(Acquisition)
        .filter(Acquisition.status.in_([AcquisitionStatus.COMPLETED, AcquisitionStatus.COMPLETED_WITH_WARNINGS]))
        .count()
    )
    failed_acq = db.query(Acquisition).filter(Acquisition.status == AcquisitionStatus.FAILED).count()
    recent_audits = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
    conn = session_manager.status()

    return {
        "total_cases": total_cases,
        "connected_devices": 1 if conn.connected else 0,
        "completed_acquisitions": completed_acq,
        "failed_acquisitions": failed_acq,
        "recent_activities": [
            {
                "id": a.id,
                "action": a.action,
                "case_id": a.case_id,
                "acquisition_id": a.acquisition_id,
                "details": a.details_json,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent_audits
        ],
    }


@router.get("/acquisitions/{acquisition_id}/contacts", response_model=PaginatedResponse)
def get_contacts(
    acquisition_id: int,
    search: str | None = Query(default=None),
    storage: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> PaginatedResponse:
    q = db.query(Contact).filter(Contact.acquisition_id == acquisition_id)
    if storage:
        q = q.filter(Contact.storage_location == storage)
    if search:
        pat = f"%{search}%"
        q = q.filter((Contact.name.ilike(pat)) | (Contact.phone_number.ilike(pat)))
    total = q.count()
    rows = q.order_by(Contact.storage_location.asc(), Contact.record_index.asc()).offset(offset).limit(limit).all()
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[ContactOut.model_validate(r).model_dump() for r in rows],
    )


@router.get("/acquisitions/{acquisition_id}/sms", response_model=PaginatedResponse)
def get_sms_messages(
    acquisition_id: int,
    search: str | None = Query(default=None),
    storage: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> PaginatedResponse:
    q = db.query(SmsMessage).filter(SmsMessage.acquisition_id == acquisition_id)
    if storage:
        q = q.filter(SmsMessage.storage_location == storage)
    if status_filter:
        q = q.filter(SmsMessage.status == status_filter)
    if date_from:
        q = q.filter(SmsMessage.timestamp_iso >= date_from)
    if date_to:
        q = q.filter(SmsMessage.timestamp_iso <= date_to)
    if search:
        pat = f"%{search}%"
        q = q.filter((SmsMessage.content.ilike(pat)) | (SmsMessage.sender_or_recipient.ilike(pat)))
    total = q.count()
    rows = q.order_by(SmsMessage.id.asc()).offset(offset).limit(limit).all()
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[SmsOut.model_validate(r).model_dump() for r in rows],
    )


@router.get("/acquisitions/{acquisition_id}/calls", response_model=PaginatedResponse)
def get_call_records(
    acquisition_id: int,
    call_type: CallType | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> PaginatedResponse:
    q = db.query(CallRecord).filter(CallRecord.acquisition_id == acquisition_id)
    if call_type is not None:
        q = q.filter(CallRecord.call_type == call_type)
    if search:
        pat = f"%{search}%"
        q = q.filter((CallRecord.phone_number.ilike(pat)) | (CallRecord.contact_name.ilike(pat)))
    total = q.count()
    rows = q.order_by(CallRecord.call_type.asc(), CallRecord.record_index.asc()).offset(offset).limit(limit).all()
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[CallRecordOut.model_validate(r).model_dump() for r in rows],
    )


@router.get("/acquisitions/{acquisition_id}/sim")
def get_sim_summary(
    acquisition_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> dict[str, Any]:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    device = db.query(Device).filter(Device.id == acq.device_id).first()
    sim_task = (
        db.query(ExtractionTask)
        .filter(ExtractionTask.acquisition_id == acquisition_id, ExtractionTask.category == TaskCategory.SIM_INFO)
        .first()
    )
    sim_contacts = db.query(Contact).filter(Contact.acquisition_id == acquisition_id, Contact.storage_location == "SM").count()
    sim_sms = db.query(SmsMessage).filter(SmsMessage.acquisition_id == acquisition_id, SmsMessage.storage_location == "SM").count()
    return {
        "acquisition_id": acquisition_id,
        "sim_capability": (device.capabilities_json or {}).get("sim_info") if device else None,
        "sim_task_status": sim_task.status.value if sim_task else "not_selected",
        "sim_contacts_count": sim_contacts,
        "sim_sms_count": sim_sms,
    }
