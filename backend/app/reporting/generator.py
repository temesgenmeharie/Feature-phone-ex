"""PDF forensic report generator and CSV/JSON evidence exporters."""

import csv
import io
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.forensics import (
    ATCommandLog,
    Acquisition,
    CallRecord,
    Case,
    Contact,
    Device,
    EvidenceFile,
    EvidenceFileType,
    Examiner,
    SmsMessage,
)
from app.preservation.vault import register_evidence_file
from app.services.audit_service import record_audit_event


def _safe(val: Any) -> str:
    return str(val) if val is not None and val != "" else "Unavailable"


def generate_pdf_report(db: Session, acquisition: Acquisition, examiner: Examiner) -> EvidenceFile:
    """Generate a professional 12-section PDF forensic examination report and hash it."""
    case = db.query(Case).filter(Case.id == acquisition.case_id).first()
    device = db.query(Device).filter(Device.id == acquisition.device_id).first()
    contacts = db.query(Contact).filter(Contact.acquisition_id == acquisition.id).all()
    sms_list = db.query(SmsMessage).filter(SmsMessage.acquisition_id == acquisition.id).all()
    calls = db.query(CallRecord).filter(CallRecord.acquisition_id == acquisition.id).all()
    at_logs = db.query(ATCommandLog).filter(ATCommandLog.acquisition_id == acquisition.id).all()
    ev_files = db.query(EvidenceFile).filter(EvidenceFile.acquisition_id == acquisition.id).all()

    out_path = Path(acquisition.evidence_dir) / f"forensic_report_{acquisition.acquisition_uid[:8]}.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=letter, title=f"Forensic Report {case.case_number if case else ''}")
    styles = getSampleStyleSheet()
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1e293b"))
    body = styles["Normal"]

    story: list[Any] = [
        Paragraph("Feature Phone Digital Forensics Examination Report", styles["Title"]),
        Spacer(1, 8),
        Paragraph(
            "<b>DISCLAIMER:</b> Logical extraction via Hayes AT commands accesses only data exposed by the "
            "device firmware over its serial interface. It does <b>not</b> recover deleted records, unallocated "
            "flash memory, or proprietary handset databases not exposed via AT commands.",
            body,
        ),
        Spacer(1, 10),
    ]

    def add_kv_section(title: str, rows: list[tuple[str, str]]) -> None:
        story.append(Paragraph(title, h2))
        tbl = Table([[k, v] for k, v in rows], colWidths=[170, 360])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(tbl)

    # 1-4: Case, Acquisition, Examiner, Device
    add_kv_section(
        "1. Case Information",
        [
            ("Case Number", _safe(case.case_number if case else None)),
            ("Title", _safe(case.title if case else None)),
            ("Purpose", _safe(case.purpose if case else None)),
            ("Device Owner Ref", _safe(case.device_owner_ref if case else None)),
        ],
    )
    add_kv_section(
        "2. Acquisition Information",
        [
            ("Acquisition UID", acquisition.acquisition_uid),
            ("Method", acquisition.extraction_method),
            ("Status", acquisition.status.value),
            ("Started At (UTC)", acquisition.started_at.isoformat()),
            ("Completed At (UTC)", _safe(acquisition.completed_at.isoformat() if acquisition.completed_at else None)),
        ],
    )
    add_kv_section(
        "3. Examiner Information",
        [
            ("Username", examiner.username),
            ("Full Name", examiner.full_name),
            ("Role", examiner.role.value),
        ],
    )
    add_kv_section(
        "4. Device Identification",
        [
            ("Port", _safe(device.port_name if device else None)),
            ("Manufacturer", _safe(device.manufacturer if device else None)),
            ("Model", _safe(device.model if device else None)),
            ("Firmware Revision", _safe(device.firmware_revision if device else None)),
            ("IMEI", _safe(device.imei if device else None)),
            ("Simulated Device", str(device.is_simulated if device else False)),
        ],
    )

    # 5-6: Methodology & Supported/Unsupported Categories
    story.append(Paragraph("5. Extraction Methodology", h2))
    story.append(
        Paragraph(
            "Read-only logical acquisition over USB/Virtual Serial COM port using validated Hayes/GSM AT commands. "
            "Destructive commands are blocked by the Command Capability Registry.",
            body,
        )
    )
    add_kv_section(
        "6. Extraction Categories (Supported / Unsupported)",
        [(t.category.value, f"{t.status.value} ({t.records_extracted} records) — {_safe(t.details)}") for t in acquisition.tasks]
        or [("None", "No tasks recorded")],
    )

    # 7. Contacts
    story.append(Paragraph(f"7. Extracted Contacts ({len(contacts)})", h2))
    if contacts:
        c_rows = [["Idx", "Storage", "Name", "Phone Number"]] + [
            [_safe(c.record_index), c.storage_location, _safe(c.name), c.phone_number] for c in contacts[:100]
        ]
        t = Table(c_rows, colWidths=[40, 60, 200, 230])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story.append(t)
    else:
        story.append(Paragraph("No contacts extracted or category unsupported.", body))

    # 8. SMS
    story.append(Paragraph(f"8. Extracted SMS Messages ({len(sms_list)})", h2))
    if sms_list:
        def _sms_parties(s):
            remote = _safe(s.sender_or_recipient)
            st = (s.status or "").upper()
            if "STO" in st or "SENT" in st:
                return "Device (Local)", remote
            return remote, "Device (Local)"

        s_rows = [["Idx", "Storage", "Status", "Sender", "Recipient", "Content"]] + [
            [
                _safe(s.message_index),
                s.storage_location,
                _safe(s.status),
                _sms_parties(s)[0],
                _sms_parties(s)[1],
                (s.content or "")[:70],
            ]
            for s in sms_list[:100]
        ]
        t = Table(s_rows, colWidths=[30, 45, 60, 100, 100, 195])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
        story.append(t)
    else:
        story.append(Paragraph("No SMS messages extracted or category unsupported.", body))

    # 9. Call Records
    story.append(Paragraph(f"9. Extracted Call Records ({len(calls)})", h2))
    if calls:
        def _call_parties(c):
            remote = f"{c.contact_name} ({c.phone_number})" if c.contact_name else c.phone_number
            if c.call_type.value == "dialed":
                return "Device (Local)", remote
            return remote, "Device (Local)"

        call_rows = [["Type", "Storage", "Sender", "Recipient", "Timestamp", "Duration"]] + [
            [
                c.call_type.value,
                c.storage_location,
                _call_parties(c)[0],
                _call_parties(c)[1],
                _safe(c.timestamp_raw),
                f"{c.duration_seconds}s" if c.duration_seconds is not None else "Unavailable",
            ]
            for c in calls[:100]
        ]
        t = Table(call_rows, colWidths=[55, 45, 120, 120, 110, 80])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
        story.append(t)
    else:
        story.append(Paragraph("No call records extracted or category unsupported.", body))

    # 10-12: Logs, Hashes, Limitations
    story.append(Paragraph(f"10. Acquisition Logs ({len(at_logs)} AT commands executed)", h2))
    story.append(Paragraph("Full verbatim AT command/response log preserved in raw_at_transcript.log.", body))

    add_kv_section(
        "11. SHA-256 Evidence Hashes",
        [(ef.file_name, ef.evidence_hash.digest_hex if ef.evidence_hash else "Unavailable") for ef in ev_files]
        or [("None", "No evidence files")],
    )

    story.append(Paragraph("12. Limitations and Technical Observations", h2))
    lims = acquisition.limitations_json or ["None recorded."]
    for lim in lims:
        story.append(Paragraph(f"- {lim}", body))

    doc.build(story)
    ev_file = register_evidence_file(
        db,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        file_path=out_path,
        file_type=EvidenceFileType.REPORT_PDF,
        is_immutable=True,
    )
    record_audit_event(
        db,
        "REPORT_GENERATED",
        examiner_id=examiner.id,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        details={"file_name": ev_file.file_name},
    )
    return ev_file


def export_csv_bundle(db: Session, acquisition: Acquisition, examiner: Examiner) -> EvidenceFile:
    """Export contacts, SMS, and call records to a unified forensic CSV artifact."""
    out_path = Path(acquisition.evidence_dir) / f"export_{acquisition.acquisition_uid[:8]}.csv"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["category", "storage", "index", "sender", "recipient", "status_or_type", "timestamp_raw", "duration", "content"])

    for c in db.query(Contact).filter(Contact.acquisition_id == acquisition.id).all():
        writer.writerow(["contact", c.storage_location, c.record_index, c.name or "", c.phone_number, c.number_type or "", "", "", ""])
    for s in db.query(SmsMessage).filter(SmsMessage.acquisition_id == acquisition.id).all():
        st = (s.status or "").upper()
        remote = s.sender_or_recipient or ""
        sender = "Device (Local)" if ("STO" in st or "SENT" in st) else remote
        recipient = remote if ("STO" in st or "SENT" in st) else "Device (Local)"
        writer.writerow(["sms", s.storage_location, s.message_index, sender, recipient, s.status or "", s.timestamp_raw or "", "", s.content or ""])
    for r in db.query(CallRecord).filter(CallRecord.acquisition_id == acquisition.id).all():
        remote = f"{r.contact_name} ({r.phone_number})" if r.contact_name else r.phone_number
        sender = "Device (Local)" if r.call_type.value == "dialed" else remote
        recipient = remote if r.call_type.value == "dialed" else "Device (Local)"
        writer.writerow(["call", r.storage_location, r.record_index, sender, recipient, r.call_type.value, r.timestamp_raw or "", r.duration_seconds or "", ""])

    out_path.write_text(buf.getvalue(), encoding="utf-8")
    ev_file = register_evidence_file(
        db,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        file_path=out_path,
        file_type=EvidenceFileType.EXPORT_CSV,
        is_immutable=True,
    )
    record_audit_event(
        db,
        "EXPORT_CSV",
        examiner_id=examiner.id,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        details={"file_name": ev_file.file_name},
    )
    return ev_file


def export_json_bundle(db: Session, acquisition: Acquisition, examiner: Examiner) -> EvidenceFile:
    """Export structured acquisition results to a JSON artifact."""
    out_path = Path(acquisition.evidence_dir) / f"export_{acquisition.acquisition_uid[:8]}.json"
    payload = {
        "acquisition_uid": acquisition.acquisition_uid,
        "case_id": acquisition.case_id,
        "status": acquisition.status.value,
        "limitations": acquisition.limitations_json or [],
        "contacts": [
            {
                "index": c.record_index,
                "storage": c.storage_location,
                "name": c.name,
                "phone_number": c.phone_number,
                "number_type": c.number_type,
            }
            for c in db.query(Contact).filter(Contact.acquisition_id == acquisition.id).all()
        ],
        "sms_messages": [
            {
                "index": s.message_index,
                "storage": s.storage_location,
                "status": s.status,
                "sender_or_recipient": s.sender_or_recipient,
                "timestamp_raw": s.timestamp_raw,
                "content": s.content,
            }
            for s in db.query(SmsMessage).filter(SmsMessage.acquisition_id == acquisition.id).all()
        ],
        "call_records": [
            {
                "index": r.record_index,
                "storage": r.storage_location,
                "call_type": r.call_type.value,
                "phone_number": r.phone_number,
                "contact_name": r.contact_name,
                "timestamp_raw": r.timestamp_raw,
                "is_cdr_level": r.is_cdr_level,
            }
            for r in db.query(CallRecord).filter(CallRecord.acquisition_id == acquisition.id).all()
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    ev_file = register_evidence_file(
        db,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        file_path=out_path,
        file_type=EvidenceFileType.EXPORT_JSON,
        is_immutable=True,
    )
    record_audit_event(
        db,
        "EXPORT_JSON",
        examiner_id=examiner.id,
        case_id=acquisition.case_id,
        acquisition_id=acquisition.id,
        details={"file_name": ev_file.file_name},
    )
    return ev_file

