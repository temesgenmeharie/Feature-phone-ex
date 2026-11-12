"""Phase 5 tests: device detection, connection, identification, and capability probing."""

from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_examiner
from app.api.routes.auth import login
from app.api.routes.cases import create_case
from app.api.routes.devices import (
    ConnectRequest,
    IdentifyRequest,
    connect_device,
    device_status,
    disconnect_device,
    get_capabilities,
    get_ports,
    identify_device,
)
from app.models.forensics import ATCommandLog, Device
from app.schemas import CaseCreate, LoginRequest
from app.serial.ports import SIMULATOR_PORT_NAME


def test_device_connect_identify_full_and_limited_profiles(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(
                case_number="CASE-2026-005",
                title="Capability Probe Test",
                purpose="Verify device identification and capability detection",
            ),
            db=db,
            current_examiner=examiner,
        )

        ports = get_ports(_=examiner)
        assert any(p.port_name == SIMULATOR_PORT_NAME for p in ports)

        # 1. Full Nokia profile
        st = connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="nokia_105_lab"),
            db=db,
            current_examiner=examiner,
        )
        assert st.connected is True
        assert device_status(_=examiner).connected is True

        ident = identify_device(IdentifyRequest(case_id=case.id), db=db, current_examiner=examiner)
        assert ident.at_ready is True
        assert ident.manufacturer == "Nokia"
        assert ident.model == "Nokia 105 (TA-1174)"
        assert ident.imei == "358912094512345"
        assert ident.capabilities["contacts"]["status"] == "supported"
        assert ident.capabilities["sms"]["status"] == "supported"
        assert ident.capabilities["call_history"]["status"] == "supported"
        assert ident.device_id is not None

        assert db.query(Device).filter(Device.id == ident.device_id).count() == 1
        assert db.query(ATCommandLog).filter(ATCommandLog.device_id == ident.device_id).count() > 0
        assert get_capabilities(_=examiner)["contacts"]["status"] == "supported"

        disconnect_device(db=db, current_examiner=examiner)
        assert device_status(_=examiner).connected is False

        # 2. Limited Itel modem profile
        connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="itel_limited_modem"),
            db=db,
            current_examiner=examiner,
        )
        ident_limited = identify_device(IdentifyRequest(case_id=case.id), db=db, current_examiner=examiner)
        assert ident_limited.manufacturer == "Itel"
        assert ident_limited.capabilities["contacts"]["status"] == "unsupported"
        assert ident_limited.capabilities["sms"]["status"] == "unsupported"
        assert ident_limited.capabilities["call_history"]["status"] == "unsupported"
        assert "AT+CPBS=?" in ident_limited.unsupported_commands

        disconnect_device(db=db, current_examiner=examiner)

