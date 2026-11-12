"""Parsers for AT command responses (CPBR, CMGL text/PDU, storage ranges, timestamps)."""

from datetime import datetime, timezone, timedelta
import re
from typing import Any

from app.extraction.pdu import decode_sms_deliver_pdu


_CPBR_RE = re.compile(r'^\+CPBR:\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*(\d+)\s*,\s*"([^"]*)"')
_CPBR_RANGE_RE = re.compile(r"\+CPBR:\s*\((\d+)-(\d+)\)")
_CMGL_TEXT_RE = re.compile(
    r'^\+CMGL:\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*(?:"[^"]*"|)\s*,\s*"([^"]*)"'
)
_CMGL_PDU_RE = re.compile(r"^\+CMGL:\s*(\d+)\s*,\s*(\d+)\s*,")


def parse_cpbr_range(lines: list[str], default_end: int = 50) -> tuple[int, int]:
    """Extract (min_idx, max_idx) from AT+CPBR=? response."""
    for ln in lines:
        m = _CPBR_RANGE_RE.search(ln)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1, default_end


def parse_cpbr_lines(lines: list[str], storage: str) -> list[dict[str, Any]]:
    """Parse +CPBR lines into structured contact/call-log dictionaries."""
    records: list[dict[str, Any]] = []
    for ln in lines:
        m = _CPBR_RE.match(ln.strip())
        if not m:
            continue
        idx = int(m.group(1))
        number = m.group(2).strip()
        num_type = m.group(3).strip()
        name = m.group(4).strip() or None
        records.append(
            {
                "record_index": idx,
                "phone_number": number,
                "number_type": num_type,
                "name": name,
                "storage_location": storage,
                "raw_entry": ln.strip(),
            }
        )
    return records


def parse_at_timestamp(ts_raw: str | None) -> datetime | None:
    """Parse GSM AT timestamp like '26/11/10,08:30:12+12' into UTC-aware datetime if valid."""
    if not ts_raw:
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2}),(\d{2}):(\d{2}):(\d{2})([+-]\d{2})?$", ts_raw.strip())
    if not m:
        return None
    yy, mm, dd, hh, mi, ss, tz_q = m.groups()
    year = 2000 + int(yy)
    tz = timezone.utc
    if tz_q:
        # GSM timezone is in quarters of an hour
        offset_minutes = int(tz_q) * 15
        tz = timezone(timedelta(minutes=offset_minutes))
    try:
        return datetime(year, int(mm), int(dd), int(hh), int(mi), int(ss), tzinfo=tz)
    except ValueError:
        return None


def parse_cmgl_text_lines(lines: list[str], storage: str) -> list[dict[str, Any]]:
    """Parse AT+CMGL text-mode header + body lines."""
    messages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for ln in lines:
        m = _CMGL_TEXT_RE.match(ln)
        if m:
            if current is not None:
                messages.append(current)
            ts_raw = m.group(4).strip() or None
            current = {
                "message_index": int(m.group(1)),
                "status": m.group(2).strip(),
                "sender_or_recipient": m.group(3).strip() or None,
                "timestamp_raw": ts_raw,
                "timestamp_iso": parse_at_timestamp(ts_raw),
                "content": "",
                "storage_location": storage,
                "pdu_hex": None,
                "raw_entry": ln,
            }
        elif current is not None:
            current["content"] = (current["content"] + "\n" + ln).strip() if current["content"] else ln
            current["raw_entry"] += "\n" + ln

    if current is not None:
        messages.append(current)
    return messages


def parse_cmgl_pdu_lines(lines: list[str], storage: str) -> list[dict[str, Any]]:
    """Parse AT+CMGL PDU-mode header + hex payload (preserving raw PDU hex)."""
    messages: list[dict[str, Any]] = []
    status_map = {"0": "REC UNREAD", "1": "REC READ", "2": "STO UNSENT", "3": "STO SENT"}
    current: dict[str, Any] | None = None

    for ln in lines:
        m = _CMGL_PDU_RE.match(ln)
        if m:
            if current is not None:
                messages.append(current)
            current = {
                "message_index": int(m.group(1)),
                "status": status_map.get(m.group(2), m.group(2)),
                "sender_or_recipient": None,
                "timestamp_raw": None,
                "timestamp_iso": None,
                "content": "[PDU payload preserved — decode offline]",
                "storage_location": storage,
                "pdu_hex": "",
                "raw_entry": ln,
            }
        elif current is not None:
            pdu_hex = ln.strip()
            current["pdu_hex"] = pdu_hex
            current["raw_entry"] += "\n" + ln
            decoded = decode_sms_deliver_pdu(pdu_hex)
            if decoded is not None:
                current["sender_or_recipient"] = decoded.sender
                current["timestamp_raw"] = decoded.timestamp_raw
                current["timestamp_iso"] = decoded.timestamp_iso
                current["content"] = decoded.text

    if current is not None:
        messages.append(current)
    return messages

