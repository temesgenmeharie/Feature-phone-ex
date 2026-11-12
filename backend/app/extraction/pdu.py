"""Offline GSM 03.40 SMS PDU decoder (7-bit default alphabet & UCS2) for feature phones."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)


@dataclass(frozen=True)
class DecodedPdu:
    sender: str | None
    timestamp_raw: str | None
    timestamp_iso: datetime | None
    text: str


def _swap_nibbles(hex_str: str) -> str:
    out = []
    for i in range(0, len(hex_str), 2):
        pair = hex_str[i : i + 2]
        if len(pair) == 2:
            out.append(pair[1] + pair[0])
    return "".join(out)


def _decode_bcd_number(hex_str: str, toa: int) -> str:
    digits = _swap_nibbles(hex_str).rstrip("Ff")
    if (toa & 0x70) == 0x10 and not digits.startswith("+"):
        return "+" + digits
    return digits


def _decode_gsm7(data: bytes, septet_count: int) -> str:
    bits = 0
    bit_count = 0
    chars: list[str] = []
    for byte in data:
        bits |= byte << bit_count
        bit_count += 8
        while bit_count >= 7 and len(chars) < septet_count:
            code = bits & 0x7F
            chars.append(_GSM7_BASIC[code] if code < len(_GSM7_BASIC) else "?")
            bits >>= 7
            bit_count -= 7
    return "".join(chars)


def _decode_scts(scts_hex: str) -> tuple[str | None, datetime | None]:
    if len(scts_hex) != 14:
        return None, None
    swapped = _swap_nibbles(scts_hex)
    try:
        yy = int(swapped[0:2])
        mm = int(swapped[2:4])
        dd = int(swapped[4:6])
        hh = int(swapped[6:8])
        mi = int(swapped[8:10])
        ss = int(swapped[10:12])
        tz_byte = int(scts_hex[12:14], 16)
        sign = -1 if (tz_byte & 0x08) else 1
        tz_nib = ((tz_byte & 0x07) * 10) + ((tz_byte >> 4) & 0x0F)
        tz = timezone(timedelta(minutes=sign * tz_nib * 15))
        raw = f"{yy:02d}/{mm:02d}/{dd:02d},{hh:02d}:{mi:02d}:{ss:02d}{'+' if sign > 0 else '-'}{tz_nib:02d}"
        return raw, datetime(2000 + yy, mm, dd, hh, mi, ss, tzinfo=tz)
    except Exception:
        return None, None


def decode_sms_deliver_pdu(pdu_hex: str) -> DecodedPdu | None:
    """Decode a standard GSM 03.40 SMS-DELIVER PDU hex string; returns None if malformed."""
    try:
        hex_clean = pdu_hex.strip().upper()
        pos = 0
        smsc_len = int(hex_clean[pos : pos + 2], 16)
        pos += 2 + smsc_len * 2

        _pdu_type = int(hex_clean[pos : pos + 2], 16)
        pos += 2

        oa_len = int(hex_clean[pos : pos + 2], 16)
        pos += 2
        oa_toa = int(hex_clean[pos : pos + 2], 16)
        pos += 2
        oa_bytes = (oa_len + 1) // 2
        oa_hex = hex_clean[pos : pos + oa_bytes * 2]
        pos += oa_bytes * 2
        sender = _decode_bcd_number(oa_hex, oa_toa)

        _pid = int(hex_clean[pos : pos + 2], 16)
        pos += 2
        dcs = int(hex_clean[pos : pos + 2], 16)
        pos += 2

        scts_hex = hex_clean[pos : pos + 14]
        pos += 14
        ts_raw, ts_iso = _decode_scts(scts_hex)

        udl = int(hex_clean[pos : pos + 2], 16)
        pos += 2
        ud_bytes = bytes.fromhex(hex_clean[pos:])

        if (dcs & 0x0C) == 0x08:
            text = ud_bytes[:udl].decode("utf-16-be", errors="replace")
        else:
            text = _decode_gsm7(ud_bytes, udl)

        return DecodedPdu(sender=sender or None, timestamp_raw=ts_raw, timestamp_iso=ts_iso, text=text)
    except Exception:
        return None

