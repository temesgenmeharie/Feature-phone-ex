"""Tests for offline GSM 03.40 SMS PDU decoder."""

from app.extraction.parsers import parse_cmgl_pdu_lines
from app.extraction.pdu import decode_sms_deliver_pdu


def test_decode_gsm7_sms_deliver_pdu():
    # Standard GSM 03.40 SMS-DELIVER PDU for "Test" from +251911223344
    pdu = "07915291000000F0040C9152911122334400006211018003212104D4F29C0E"
    decoded = decode_sms_deliver_pdu(pdu)
    assert decoded is not None
    assert decoded.sender == "+251911223344"
    assert decoded.text == "Test"

    parsed = parse_cmgl_pdu_lines(["+CMGL: 1,1,,28", pdu], storage="SM")
    assert len(parsed) == 1
    assert parsed[0]["content"] == "Test"
    assert parsed[0]["sender_or_recipient"] == "+251911223344"
    assert parsed[0]["pdu_hex"] == pdu
