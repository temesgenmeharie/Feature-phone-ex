"""Extraction Management Orchestrator coordinating logical acquisition & DB persistence."""

from datetime import datetime, timezone
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.extraction.extractors import EXTRACTOR_REGISTRY
from app.extraction.interfaces import (
    ExtractionCategory,
    ExtractionContext,
    ExtractionOutcome,
    ExtractionStatus,
)
from app.models.forensics import (
    ATCommandLog,
    Acquisition,
    AcquisitionStatus,
    CallRecord,
    CallType,
    Contact,
    Device,
    Examiner,
    ExtractionTask,
    SmsMessage,
    TaskCategory,
    TaskStatus,
)
from app.serial.engine import ATCommandEngine
from app.serial.transport import SerialTransportError
from app.preservation.vault import preserve_acquisition_evidence
from app.services.audit_service import record_audit_event


class ExtractionOrchestrator:
    """Runs selected extractor plugins, persists structured records, and captures raw AT artifacts."""

    def run_acquisition(
        self,
        db: Session,
        engine: ATCommandEngine,
        *,
        case_id: int,
        device: Device,
        examiner: Examiner,
        categories: list[ExtractionCategory],
    ) -> tuple[Acquisition, dict[str, dict[str, str]]]:
        acq_uid = str(uuid.uuid4())
        evidence_dir = Path(settings.evidence_dir) / f"case_{case_id}" / f"acq_{acq_uid}"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Pre-flight check: ensure the connected port actually responds to AT
        handshake = engine.send_command("AT", timeout_s=2.0)
        if not handshake.is_ok:
            raise SerialTransportError(
                f"Cannot extract data: No responsive feature phone detected on port {engine.transport.port_name}. "
                "The port did not reply to AT commands. Please connect an authorized feature phone, power it on, "
                "and ensure its USB mode is set to 'COM Port / Modem / PC Suite'."
            )

        acquisition = Acquisition(
            acquisition_uid=acq_uid,
            case_id=case_id,
            device_id=device.id,
            examiner_id=examiner.id,
            extraction_method="AT_LOGICAL",
            status=AcquisitionStatus.RUNNING,
            evidence_dir=str(evidence_dir),
            started_at=datetime.now(timezone.utc),
        )
        db.add(acquisition)
        db.commit()
        db.refresh(acquisition)

        record_audit_event(
            db,
            "ACQUISITION_STARTED",
            examiner_id=examiner.id,
            case_id=case_id,
            acquisition_id=acquisition.id,
            details={"categories": [c.value for c in categories], "acquisition_uid": acq_uid},
        )

        context = ExtractionContext(
            case_id=case_id,
            acquisition_id=acquisition.id,
            acquisition_uid=acq_uid,
            evidence_dir=str(evidence_dir),
        )

        all_limitations: list[str] = []
        raw_artifacts_by_cat: dict[str, dict[str, str]] = {}
        any_failed = False
        any_warnings = False
        log_cursor = len(engine.logs)

        for cat in categories:
            plugin = EXTRACTOR_REGISTRY[cat]
            task = ExtractionTask(
                acquisition_id=acquisition.id,
                category=TaskCategory(cat.value),
                status=TaskStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            try:
                outcome: ExtractionOutcome = plugin.extract(engine, context)
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.details = str(exc)
                task.completed_at = datetime.now(timezone.utc)
                db.commit()
                any_failed = True
                all_limitations.append(f"{cat.value}: {exc}")
                continue

            raw_artifacts_by_cat[cat.value] = outcome.raw_artifacts
            all_limitations.extend(outcome.limitations)
            self._persist_records(db, case_id=case_id, acquisition_id=acquisition.id, outcome=outcome)

            task.status = TaskStatus(outcome.status.value)
            task.records_extracted = len(outcome.records)
            task.details = "; ".join(outcome.limitations) if outcome.limitations else None
            task.completed_at = datetime.now(timezone.utc)
            db.commit()

            if outcome.status in (ExtractionStatus.PARTIAL, ExtractionStatus.UNSUPPORTED):
                any_warnings = True
            elif outcome.status == ExtractionStatus.FAILED:
                any_failed = True

        # Persist AT command logs generated during this acquisition
        for entry in engine.logs[log_cursor:]:
            db.add(
                ATCommandLog(
                    acquisition_id=acquisition.id,
                    device_id=device.id,
                    command=entry.command,
                    response=entry.raw_response,
                    terminal_status=entry.terminal_status,
                    duration_ms=entry.duration_ms,
                    executed_at=entry.executed_at,
                )
            )

        acquisition.completed_at = datetime.now(timezone.utc)
        acquisition.limitations_json = all_limitations
        if any_failed:
            acquisition.status = AcquisitionStatus.COMPLETED_WITH_WARNINGS
        elif any_warnings:
            acquisition.status = AcquisitionStatus.COMPLETED_WITH_WARNINGS
        else:
            acquisition.status = AcquisitionStatus.COMPLETED
        db.commit()
        db.refresh(acquisition)

        preserve_acquisition_evidence(db, acquisition, raw_artifacts_by_cat)

        record_audit_event(
            db,
            "ACQUISITION_COMPLETED",
            examiner_id=examiner.id,
            case_id=case_id,
            acquisition_id=acquisition.id,
            details={"status": acquisition.status.value},
        )
        return acquisition, raw_artifacts_by_cat

    @staticmethod
    def _persist_records(db: Session, *, case_id: int, acquisition_id: int, outcome: ExtractionOutcome) -> None:
        if outcome.category == ExtractionCategory.CONTACTS:
            for rec in outcome.records:
                db.add(
                    Contact(
                        case_id=case_id,
                        acquisition_id=acquisition_id,
                        record_index=rec.get("record_index"),
                        name=rec.get("name"),
                        phone_number=rec["phone_number"],
                        number_type=rec.get("number_type"),
                        storage_location=rec.get("storage_location", "Unknown"),
                        raw_entry=rec.get("raw_entry"),
                    )
                )
        elif outcome.category == ExtractionCategory.SMS:
            for rec in outcome.records:
                db.add(
                    SmsMessage(
                        case_id=case_id,
                        acquisition_id=acquisition_id,
                        message_index=rec.get("message_index"),
                        status=rec.get("status"),
                        sender_or_recipient=rec.get("sender_or_recipient"),
                        timestamp_raw=rec.get("timestamp_raw"),
                        timestamp_iso=rec.get("timestamp_iso"),
                        content=rec.get("content"),
                        storage_location=rec.get("storage_location", "Unknown"),
                        pdu_hex=rec.get("pdu_hex"),
                        raw_entry=rec.get("raw_entry"),
                    )
                )
        elif outcome.category == ExtractionCategory.CALL_HISTORY:
            for rec in outcome.records:
                db.add(
                    CallRecord(
                        case_id=case_id,
                        acquisition_id=acquisition_id,
                        call_type=CallType(rec.get("call_type", "unknown")),
                        record_index=rec.get("record_index"),
                        phone_number=rec["phone_number"],
                        contact_name=rec.get("contact_name"),
                        timestamp_raw=rec.get("timestamp_raw"),
                        timestamp_iso=rec.get("timestamp_iso"),
                        duration_seconds=rec.get("duration_seconds"),
                        storage_location=rec.get("storage_location", "Unknown"),
                        is_cdr_level=bool(rec.get("is_cdr_level", False)),
                        raw_entry=rec.get("raw_entry"),
                    )
                )
        db.commit()
