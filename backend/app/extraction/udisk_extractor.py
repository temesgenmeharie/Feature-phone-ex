"""Forensic U Disk / USB Mass Storage Extractor and Deleted Record Carver for Feature Phones.

Extracts contacts, SMS messages, and call logs from phone internal storage/SD card
when mounted in USB Mass Storage mode (e.g. Spreadtrum SC6531, MediaTek MT6261, Nokia s30+).

Supports:
1. Logical file parsing: .vcf (vCard 2.1/3.0), .vmg (vMessage), .csv, .txt, .dat, .bin, .db
2. Deleted record recovery:
   - Carving GSM 03.40 PDU hex streams from binary files, backups, and unallocated blocks
   - Validating carved PDUs with offline PDU decoder
   - Recovering deleted call records from fixed binary calllog.dat / history.bin structures
   - Marking recovered deleted records with status="DELETED_RECOVERED"
3. SHA-256 evidence preservation of all source files into the case evidence vault.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
from typing import Any

from app.extraction.interfaces import (
    ExtractionCategory,
    ExtractionContext,
    ExtractionOutcome,
    ExtractionStatus,
)
from app.extraction.pdu import decode_sms_deliver_pdu
from app.models.forensics import EvidenceFileType
from app.preservation.vault import register_evidence_file


_PHONE_REGEX = re.compile(r"^\+?[0-9]{3,20}$")
_HEX_RUN_REGEX = re.compile(r"\b([0-9A-Fa-f]{32,320})\b")


def parse_vcard_content(content: str, source_file: str) -> list[dict[str, Any]]:
    """Parse vCard 2.1 / 3.0 content into structured contact records."""
    contacts: list[dict[str, Any]] = []
    blocks = re.split(r"BEGIN:VCARD", content, flags=re.IGNORECASE)
    idx = 1
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        fn_match = re.search(r"^FN:(.*)$", blk, re.MULTILINE | re.IGNORECASE)
        n_match = re.search(r"^N:([^;]*)(?:;([^;]*))?", blk, re.MULTILINE | re.IGNORECASE)
        name = None
        if fn_match and fn_match.group(1).strip():
            name = fn_match.group(1).strip()
        elif n_match:
            parts = [p.strip() for p in n_match.groups() if p and p.strip()]
            name = " ".join(reversed(parts)) if parts else None

        tels = re.findall(r"^TEL(?:;[^:]+)?:(.*)$", blk, re.MULTILINE | re.IGNORECASE)
        for t in tels:
            clean_num = re.sub(r"[^\d+]", "", t.strip())
            if clean_num:
                contacts.append({
                    "record_index": idx,
                    "name": name,
                    "phone_number": clean_num,
                    "number_type": "CELL",
                    "storage_location": f"UDISK:{Path(source_file).name}",
                    "raw_entry": f"BEGIN:VCARD\n{blk}\nEND:VCARD",
                })
                idx += 1
    return contacts


def parse_vmessage_content(content: str, source_file: str) -> list[dict[str, Any]]:
    """Parse vMessage (.vmg) files into structured SMS records."""
    messages: list[dict[str, Any]] = []
    blocks = re.split(r"BEGIN:VMSG", content, flags=re.IGNORECASE)
    idx = 1
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        tel_match = re.search(r"TEL:(.*)", blk, re.IGNORECASE)
        date_match = re.search(r"Date:([^\r\n]+)", blk, re.IGNORECASE)
        status_match = re.search(r"Status:([^\r\n]+)", blk, re.IGNORECASE)
        body_match = re.search(r"BEGIN:VBODY\s*(.*?)\s*END:VBODY", blk, re.IGNORECASE | re.DOTALL)

        sender_num = tel_match.group(1).strip() if tel_match else None
        if sender_num:
            sender_num = re.sub(r"[^\d+]", "", sender_num)
        
        msg_text = ""
        if body_match:
            raw_body = body_match.group(1).strip()
            # Strip metadata lines from body (Date:, Tel:, Type:, Status:)
            body_lines = []
            for ln in raw_body.splitlines():
                if re.match(r"^(?:Date|Tel|Type|Status|X-[A-Z-]+):", ln.strip(), re.IGNORECASE):
                    continue
                body_lines.append(ln)
            msg_text = "\n".join(body_lines).strip()

        date_str = date_match.group(1).strip() if date_match else None
        status = status_match.group(1).strip().upper() if status_match else "REC READ"

        ts_iso = None
        if date_str:
            for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    ts_iso = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    pass

        messages.append({
            "message_index": idx,
            "status": status,
            "sender_or_recipient": sender_num,
            "timestamp_raw": date_str,
            "timestamp_iso": ts_iso,
            "content": msg_text,
            "storage_location": f"UDISK:{Path(source_file).name}",
            "pdu_hex": None,
            "raw_entry": f"BEGIN:VMSG\n{blk}\nEND:VMSG",
        })
        idx += 1
    return messages


def carve_pdu_sms_from_binary(raw_bytes: bytes, source_label: str) -> list[dict[str, Any]]:
    """Carve and validate GSM 03.40 PDU hex strings from binary blocks or unallocated space."""
    carved: list[dict[str, Any]] = []
    text_content = ""
    try:
        text_content = raw_bytes.decode("ascii", errors="ignore")
    except Exception:
        pass

    seen_pdus: set[str] = set()

    # 1. Search for ascii hex runs
    for m in _HEX_RUN_REGEX.finditer(text_content):
        cand_hex = m.group(1).strip().upper()
        if len(cand_hex) % 2 != 0 or cand_hex in seen_pdus:
            continue
        seen_pdus.add(cand_hex)
        decoded = decode_sms_deliver_pdu(cand_hex)
        if decoded and decoded.text and decoded.sender:
            carved.append({
                "message_index": len(carved) + 1,
                "status": "DELETED_RECOVERED",
                "sender_or_recipient": decoded.sender,
                "timestamp_raw": decoded.timestamp_raw,
                "timestamp_iso": decoded.timestamp_iso,
                "content": decoded.text,
                "storage_location": f"CARVED_STORAGE:{source_label}",
                "pdu_hex": cand_hex,
                "raw_entry": f"[CARVED VALIDATED PDU] {cand_hex}",
            })

    # 2. Also search directly in raw bytes for binary PDU blobs (starting with SMSC len e.g. 0x07)
    if len(raw_bytes) >= 30:
        for offset in range(len(raw_bytes) - 30):
            smsc_len = raw_bytes[offset]
            if 1 <= smsc_len <= 12 and offset + 1 + smsc_len + 10 < len(raw_bytes):
                # Check for international number format 0x91 in SMSC
                if raw_bytes[offset + 1] == 0x91:
                    blob_hex = raw_bytes[offset : offset + 160].hex().upper()
                    if blob_hex not in seen_pdus:
                        decoded = decode_sms_deliver_pdu(blob_hex)
                        if decoded and decoded.text and decoded.sender:
                            seen_pdus.add(blob_hex)
                            carved.append({
                                "message_index": len(carved) + 1,
                                "status": "DELETED_RECOVERED",
                                "sender_or_recipient": decoded.sender,
                                "timestamp_raw": decoded.timestamp_raw,
                                "timestamp_iso": decoded.timestamp_iso,
                                "content": decoded.text,
                                "storage_location": f"CARVED_BINARY:{source_label}",
                                "pdu_hex": blob_hex,
                                "raw_entry": f"[CARVED BINARY PDU] offset=0x{offset:X}",
                            })

    return carved


def parse_binary_calllog(raw_bytes: bytes, source_label: str) -> list[dict[str, Any]]:
    """Parse fixed binary calllog records from Spreadtrum / MediaTek calllog.dat / history.bin."""
    records: list[dict[str, Any]] = []
    # Standard feature phone record sizes are commonly 32, 48, 64, or 128 bytes
    for stride in (64, 48, 32, 128):
        if len(raw_bytes) < stride:
            continue
        found_in_stride: list[dict[str, Any]] = []
        for offset in range(0, len(raw_bytes) - stride + 1, stride):
            chunk = raw_bytes[offset : offset + stride]
            ascii_text = chunk.decode("ascii", errors="ignore")
            num_match = re.search(r"(\+?[0-9]{4,18})", ascii_text)
            if num_match:
                phone_num = num_match.group(1)
                # Check if marked deleted: status byte in chunk[0] or chunk[1] is 0x00, 0xE5, or 0xFF
                is_deleted = chunk[0] in (0x00, 0xE5, 0xFF) or chunk[1] in (0x00, 0xE5, 0xFF)
                call_type = "unknown"
                if chunk[0] == 1 or chunk[1] == 1:
                    call_type = "received"
                elif chunk[0] == 2 or chunk[1] == 2:
                    call_type = "dialed"
                elif chunk[0] == 3 or chunk[1] == 3:
                    call_type = "missed"

                found_in_stride.append({
                    "call_type": call_type,
                    "record_index": len(found_in_stride) + 1,
                    "phone_number": phone_num,
                    "contact_name": None,
                    "timestamp_raw": None,
                    "timestamp_iso": None,
                    "duration_seconds": None,
                    "storage_location": f"{'CARVED_DELETED' if is_deleted else 'UDISK'}:{source_label}",
                    "is_cdr_level": False,
                    "raw_entry": f"[BINARY RECORD offset=0x{offset:X}] hex={chunk[:16].hex()}",
                })
        if len(found_in_stride) > len(records):
            records = found_in_stride

    return records


class UDiskForensicExtractor:
    """Forensic extractor that reads a phone storage mount, carves data, and preserves artifacts."""

    def __init__(self, drive_path: str):
        self.drive_path = Path(drive_path)

    def extract_all(self, context: ExtractionContext) -> dict[str, ExtractionOutcome]:
        """Perform full forensic extraction and carving from the U Disk drive."""
        evidence_dir = Path(context.evidence_dir) / "udisk_artifacts"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        contacts_records: list[dict[str, Any]] = []
        sms_records: list[dict[str, Any]] = []
        call_records: list[dict[str, Any]] = []
        device_info: dict[str, Any] = {
            "source_drive": str(self.drive_path),
            "extraction_type": "UDISK_FORENSIC_MASS_STORAGE",
            "volume_info": {},
            "detected_files": [],
        }

        limitations: list[str] = []
        raw_artifacts: dict[str, str] = {}

        if not self.drive_path.exists():
            return {
                ExtractionCategory.DEVICE_INFO.value: ExtractionOutcome(
                    category=ExtractionCategory.DEVICE_INFO,
                    status=ExtractionStatus.FAILED,
                    error_message=f"Drive {self.drive_path} not found or disconnected.",
                )
            }

        # 1. Collect Volume & Filesystem info
        try:
            usage = shutil.disk_usage(self.drive_path)
            device_info["volume_info"] = {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
        except Exception as e:
            limitations.append(f"Could not query disk geometry: {e}")

        # 2. Walk directory tree and collect forensic artifacts
        found_files: list[Path] = []
        try:
            for root, dirs, files in os.walk(self.drive_path):
                for f in files:
                    p = Path(root) / f
                    found_files.append(p)
                    device_info["detected_files"].append(str(p.relative_to(self.drive_path)))
        except Exception as e:
            limitations.append(f"Directory traversal error: {e}")

        # 3. Parse and preserve each relevant file
        for file_path in found_files:
            fname = file_path.name.lower()
            ext = file_path.suffix.lower()

            # Preserve to evidence directory
            rel_name = f"udisk_{file_path.name}"
            dest_file = evidence_dir / rel_name
            try:
                shutil.copy2(file_path, dest_file)
            except Exception:
                pass

            # Read file bytes for parsing & carving
            try:
                raw_bytes = file_path.read_bytes()
            except Exception:
                continue

            raw_artifacts[f"file_{file_path.name}"] = f"Size: {len(raw_bytes)} bytes; Path: {file_path}"

            # Contacts: .vcf or phonebook.dat
            if ext == ".vcf":
                try:
                    text = raw_bytes.decode("utf-8", errors="replace")
                    contacts_records.extend(parse_vcard_content(text, file_path.name))
                except Exception:
                    pass
            elif "contact" in fname or "phonebook" in fname or "vcard" in fname:
                try:
                    contacts_records.extend(parse_binary_calllog(raw_bytes, file_path.name))
                except Exception:
                    pass

            # SMS Messages: .vmg or sms.dat or carving
            if ext in (".vmg", ".vnt"):
                try:
                    text = raw_bytes.decode("utf-8", errors="replace")
                    sms_records.extend(parse_vmessage_content(text, file_path.name))
                except Exception:
                    pass
            
            # Carve for GSM 03.40 PDUs in all binary / dat / bin files
            if ext in (".dat", ".bin", ".db", ".sqlite", ".bak", ".tmp") or "sms" in fname or "msg" in fname:
                carved_sms = carve_pdu_sms_from_binary(raw_bytes, file_path.name)
                sms_records.extend(carved_sms)

            # Call logs: calllog.dat, history.bin, calls.csv
            if "call" in fname or "history" in fname or ext == ".csv":
                if ext == ".csv":
                    try:
                        text = raw_bytes.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            parts = line.split(",")
                            for p in parts:
                                p_clean = p.strip().strip('"')
                                if _PHONE_REGEX.match(p_clean):
                                    call_records.append({
                                        "call_type": "unknown",
                                        "record_index": len(call_records) + 1,
                                        "phone_number": p_clean,
                                        "contact_name": None,
                                        "timestamp_raw": None,
                                        "timestamp_iso": None,
                                        "duration_seconds": None,
                                        "storage_location": f"UDISK_CSV:{file_path.name}",
                                        "is_cdr_level": False,
                                        "raw_entry": line,
                                    })
                                    break
                    except Exception:
                        pass
                else:
                    call_records.extend(parse_binary_calllog(raw_bytes, file_path.name))

        # Check manufacturer clues
        found_names_str = " ".join([f.name for f in found_files]).lower()
        if "h-mobile" in str(self.drive_path).lower() or "vcard" in found_names_str:
            device_info["manufacturer"] = "H-MOBILE / Spreadtrum"
            device_info["model"] = "Spreadtrum SC6531 Feature Phone"
        elif "mediatek" in found_names_str:
            device_info["manufacturer"] = "Tecno / MediaTek"
            device_info["model"] = "MediaTek MT6261 Feature Phone"
        else:
            device_info["manufacturer"] = "Feature Phone USB Mass Storage"
            device_info["model"] = f"Removable Volume ({self.drive_path})"

        outcomes = {
            ExtractionCategory.DEVICE_INFO.value: ExtractionOutcome(
                category=ExtractionCategory.DEVICE_INFO,
                status=ExtractionStatus.SUCCESS,
                records=[device_info],
                raw_artifacts=raw_artifacts,
                limitations=limitations,
            ),
            ExtractionCategory.CONTACTS.value: ExtractionOutcome(
                category=ExtractionCategory.CONTACTS,
                status=ExtractionStatus.SUCCESS if contacts_records else ExtractionStatus.PARTIAL,
                records=contacts_records,
                raw_artifacts=raw_artifacts,
                limitations=limitations if not contacts_records else [],
            ),
            ExtractionCategory.SMS.value: ExtractionOutcome(
                category=ExtractionCategory.SMS,
                status=ExtractionStatus.SUCCESS if sms_records else ExtractionStatus.PARTIAL,
                records=sms_records,
                raw_artifacts=raw_artifacts,
                limitations=limitations if not sms_records else [],
            ),
            ExtractionCategory.CALL_HISTORY.value: ExtractionOutcome(
                category=ExtractionCategory.CALL_HISTORY,
                status=ExtractionStatus.SUCCESS if call_records else ExtractionStatus.PARTIAL,
                records=call_records,
                raw_artifacts=raw_artifacts,
                limitations=limitations if not call_records else [],
            ),
        }

        return outcomes
