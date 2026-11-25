"""Tests for U-Disk forensic extraction, deleted PDU carving, and USB connection mode detection."""

from pathlib import Path
import pytest
from app.extraction.interfaces import ExtractionCategory, ExtractionContext, ExtractionStatus
from app.extraction.udisk_extractor import (
    UDiskForensicExtractor,
    parse_vcard_content,
    parse_vmessage_content,
    carve_pdu_sms_from_binary,
    parse_binary_calllog,
)
from app.serial.detector import (
    detect_usb_connection_mode,
    UDiskDriveInfo,
    DriverProblemDevice,
    USBModeReport,
)


def test_parse_vcard_content():
    sample_vcard = """
BEGIN:VCARD
VERSION:2.1
N:Meharie;Temesgen;;;
FN:Temesgen Meharie
TEL;CELL:+251911223344
TEL;HOME:0115512345
END:VCARD

BEGIN:VCARD
VERSION:3.0
FN:Forensic Lab
TEL;TYPE=CELL:0988776655
END:VCARD
"""
    records = parse_vcard_content(sample_vcard, "contacts.vcf")
    assert len(records) == 3
    assert records[0]["phone_number"] == "+251911223344"
    assert records[0]["name"] == "Temesgen Meharie"
    assert records[1]["phone_number"] == "0115512345"
    assert records[2]["phone_number"] == "0988776655"
    assert records[2]["name"] == "Forensic Lab"


def test_parse_vmessage_content():
    sample_vmsg = """
BEGIN:VMSG
VERSION:1.1
BEGIN:VCARD
TEL:+251922334455
END:VCARD
BEGIN:VBODY
Date:2026/11/20 14:30:00
Status:READ
Evidence message retrieved from handset
END:VBODY
END:VMSG
"""
    records = parse_vmessage_content(sample_vmsg, "sms_001.vmg")
    assert len(records) == 1
    assert records[0]["sender_or_recipient"] == "+251922334455"
    assert "Evidence message retrieved" in records[0]["content"]
    assert records[0]["status"] == "READ"
    assert records[0]["timestamp_iso"] is not None


def test_carve_pdu_sms_from_binary():
    # PDU hex for SMS-DELIVER from +251911223344 with text "Hello"
    # Format: SMSC(07 91 ...) + Type(04) + Originator(0C 91 ...) + PID(00) + DCS(00) + SCTS(7 bytes) + UDL(05) + UD(packed)
    # A valid GSM 03.40 PDU:
    valid_pdu = "07915291112233F4040C915291112233F400006211024103000005C8329BFD06"
    raw_blob = b"Random binary data \x00\xFF\xAA" + valid_pdu.encode("ascii") + b"\x00\x00 slack data"
    
    carved = carve_pdu_sms_from_binary(raw_blob, "test_slack.bin")
    assert len(carved) >= 1
    assert carved[0]["status"] == "DELETED_RECOVERED"
    assert carved[0]["sender_or_recipient"] is not None
    assert carved[0]["content"] == "Hello"


def test_parse_binary_calllog():
    # Create 64-byte structured record with call type byte, status byte, and phone number
    chunk1 = bytes([1, 1]) + b"+251911002233" + (b"\x00" * 18) + (b"\x00" * 31)
    chunk2 = bytes([3, 0xE5]) + b"+251922446688" + (b"\x00" * 18) + (b"\x00" * 31)  # deleted missed call
    raw = chunk1 + chunk2
    records = parse_binary_calllog(raw, "calllog.dat")
    assert len(records) == 2
    assert records[0]["call_type"] == "received"
    assert records[0]["phone_number"] == "+251911002233"
    assert records[1]["call_type"] == "missed"
    assert records[1]["phone_number"] == "+251922446688"
    assert "CARVED_DELETED" in records[1]["storage_location"]


def test_udisk_extractor_full_directory(tmp_path: Path):
    # Simulate a phone storage directory
    vcard_dir = tmp_path / "vCard"
    vcard_dir.mkdir()
    (vcard_dir / "contacts.vcf").write_text(
        "BEGIN:VCARD\nVERSION:2.1\nFN:Abebe\nTEL;CELL:0911001122\nEND:VCARD",
        encoding="utf-8"
    )
    (tmp_path / "sms.vmg").write_text(
        "BEGIN:VMSG\nBEGIN:VCARD\nTEL:0922334455\nEND:VCARD\nBEGIN:VBODY\nDate:2026/11/20 10:00:00\nMeeting confirmed\nEND:VBODY\nEND:VMSG",
        encoding="utf-8"
    )

    extractor = UDiskForensicExtractor(str(tmp_path))
    context = ExtractionContext(
        case_id=1,
        acquisition_id=1,
        acquisition_uid="test-uid-123",
        evidence_dir=str(tmp_path / "evidence"),
    )
    outcomes = extractor.extract_all(context)
    
    assert ExtractionCategory.CONTACTS.value in outcomes
    assert len(outcomes[ExtractionCategory.CONTACTS.value].records) == 1
    assert outcomes[ExtractionCategory.CONTACTS.value].records[0]["phone_number"] == "0911001122"

    assert ExtractionCategory.SMS.value in outcomes
    assert len(outcomes[ExtractionCategory.SMS.value].records) == 1
    assert outcomes[ExtractionCategory.SMS.value].records[0]["content"] == "Meeting confirmed"
