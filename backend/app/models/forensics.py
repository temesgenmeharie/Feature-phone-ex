"""SQLAlchemy ORM models for all 12 forensic database entities."""

from datetime import datetime, timezone
import enum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExaminerRole(str, enum.Enum):
    ADMIN = "admin"
    EXAMINER = "examiner"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    ARCHIVED = "archived"


class AcquisitionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCategory(str, enum.Enum):
    DEVICE_INFO = "device_info"
    CONTACTS = "contacts"
    SMS = "sms"
    CALL_HISTORY = "call_history"
    SIM_INFO = "sim_info"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUPPORTED_SUCCESS = "supported_success"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    SKIPPED = "skipped"


class CallType(str, enum.Enum):
    MISSED = "missed"
    RECEIVED = "received"
    DIALED = "dialed"
    UNKNOWN = "unknown"


class EvidenceFileType(str, enum.Enum):
    RAW_AT_LOG = "raw_at_log"
    RAW_RESPONSE = "raw_response"
    MANIFEST = "manifest"
    EXPORT_CSV = "export_csv"
    EXPORT_JSON = "export_json"
    REPORT_PDF = "report_pdf"


class Examiner(Base):
    __tablename__ = "examiners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[ExaminerRole] = mapped_column(SAEnum(ExaminerRole), default=ExaminerRole.EXAMINER, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cases: Mapped[list["Case"]] = relationship(back_populates="lead_examiner")
    acquisitions: Mapped[list["Acquisition"]] = relationship(back_populates="examiner")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    device_owner_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CaseStatus] = mapped_column(SAEnum(CaseStatus), default=CaseStatus.OPEN, nullable=False)
    lead_examiner_id: Mapped[int] = mapped_column(ForeignKey("examiners.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    lead_examiner: Mapped["Examiner"] = relationship(back_populates="cases")
    devices: Mapped[list["Device"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    acquisitions: Mapped[list["Acquisition"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    port_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    baud_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    firmware_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imei: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capabilities_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="devices")
    acquisitions: Mapped[list["Acquisition"]] = relationship(back_populates="device")


class Acquisition(Base):
    __tablename__ = "acquisitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    acquisition_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    examiner_id: Mapped[int] = mapped_column(ForeignKey("examiners.id"), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), default="AT_LOGICAL", nullable=False)
    status: Mapped[AcquisitionStatus] = mapped_column(
        SAEnum(AcquisitionStatus), default=AcquisitionStatus.PENDING, nullable=False
    )
    evidence_dir: Mapped[str] = mapped_column(String(512), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limitations_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="acquisitions")
    device: Mapped["Device"] = relationship(back_populates="acquisitions")
    examiner: Mapped["Examiner"] = relationship(back_populates="acquisitions")
    tasks: Mapped[list["ExtractionTask"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")
    sms_messages: Mapped[list["SmsMessage"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")
    call_records: Mapped[list["CallRecord"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")
    evidence_files: Mapped[list["EvidenceFile"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")
    at_logs: Mapped[list["ATCommandLog"]] = relationship(back_populates="acquisition", cascade="all, delete-orphan")


class ExtractionTask(Base):
    __tablename__ = "extraction_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    acquisition_id: Mapped[int] = mapped_column(ForeignKey("acquisitions.id"), nullable=False, index=True)
    category: Mapped[TaskCategory] = mapped_column(SAEnum(TaskCategory), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    records_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="tasks")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    acquisition_id: Mapped[int] = mapped_column(ForeignKey("acquisitions.id"), nullable=False, index=True)
    record_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    number_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_location: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_entry: Mapped[str | None] = mapped_column(Text, nullable=True)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="contacts")


class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    acquisition_id: Mapped[int] = mapped_column(ForeignKey("acquisitions.id"), nullable=False, index=True)
    message_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_or_recipient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp_iso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_location: Mapped[str] = mapped_column(String(32), nullable=False)
    pdu_hex: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_entry: Mapped[str | None] = mapped_column(Text, nullable=True)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="sms_messages")


class CallRecord(Base):
    __tablename__ = "call_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    acquisition_id: Mapped[int] = mapped_column(ForeignKey("acquisitions.id"), nullable=False, index=True)
    call_type: Mapped[CallType] = mapped_column(SAEnum(CallType), default=CallType.UNKNOWN, nullable=False)
    record_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp_iso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_location: Mapped[str] = mapped_column(String(32), nullable=False)
    is_cdr_level: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_entry: Mapped[str | None] = mapped_column(Text, nullable=True)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="call_records")


class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    acquisition_id: Mapped[int] = mapped_column(ForeignKey("acquisitions.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[EvidenceFileType] = mapped_column(SAEnum(EvidenceFileType), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="evidence_files")
    evidence_hash: Mapped["EvidenceHash | None"] = relationship(
        back_populates="evidence_file", uselist=False, cascade="all, delete-orphan"
    )


class EvidenceHash(Base):
    __tablename__ = "evidence_hashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_file_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id"), unique=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), default="SHA-256", nullable=False)
    digest_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verification_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    evidence_file: Mapped["EvidenceFile"] = relationship(back_populates="evidence_hash")


class ATCommandLog(Base):
    __tablename__ = "at_command_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    acquisition_id: Mapped[int | None] = mapped_column(ForeignKey("acquisitions.id"), nullable=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    command: Mapped[str] = mapped_column(String(255), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    terminal_status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    acquisition: Mapped["Acquisition | None"] = relationship(back_populates="at_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examiner_id: Mapped[int | None] = mapped_column(ForeignKey("examiners.id"), nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    acquisition_id: Mapped[int | None] = mapped_column(ForeignKey("acquisitions.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

