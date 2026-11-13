"""Phase 6 tests: logical data extraction across full and limited simulated devices."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_examiner
from app.api.routes.auth import login
from app.api.routes.cases import create_case
from app.api.routes.devices import ConnectRequest, IdentifyRequest, connect_device, disconnect_device, identify_device
from app.extraction.interfaces import ExtractionCategory
from app.extraction.orchestrator import ExtractionOrchestrator
from app.models.forensics import (
    AcquisitionStatus,
    CallRecord,
    Contact,
    Device,
    SmsMessage,
    TaskStatus,
)
from app.schemas import CaseCreate, LoginRequest
from app.serial.manager import session_manager
from app.serial.ports import SIMULATOR_PORT_NAME


def test_logical_extraction_full_nokia_profile(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(case_number="CASE-2026-006", title="Full Extraction Test", purpose="Lab verification"),
            db=db,
            current_examiner=examiner,
        )

        connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="nokia_105_lab"),
            db=db,
            current_examiner=examiner,
        )
        ident = identify_device(IdentifyRequest(case_id=case.id), db=db, current_examiner=examiner)
        device = db.query(Device).filter(Device.id == ident.device_id).first()

        acq, raw_artifacts = ExtractionOrchestrator().run_acquisition(
            db,
            session_manager.require_engine(),
            case_id=case.id,
            device=device,
            examiner=examiner,
            categories=list(ExtractionCategory),
        )
        assert acq.status == AcquisitionStatus.COMPLETED
        assert db.query(Contact).filter(Contact.acquisition_id == acq.id).count() == 4
        assert db.query(SmsMessage).filter(SmsMessage.acquisition_id == acq.id).count() == 3
        calls = db.query(CallRecord).filter(CallRecord.acquisition_id == acq.id).all()
        assert len(calls) == 5
        assert all(c.is_cdr_level is False for c in calls)
        assert "contacts" in raw_artifacts
        disconnect_device(db=db, current_examiner=examiner)


def test_logical_extraction_limited_itel_marks_unsupported(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(case_number="CASE-2026-006B", title="Limited Modem Test", purpose="Unsupported check"),
            db=db,
            current_examiner=examiner,
        )

        connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="itel_limited_modem"),
            db=db,
            current_examiner=examiner,
        )
        ident = identify_device(IdentifyRequest(case_id=case.id), db=db, current_examiner=examiner)
        device = db.query(Device).filter(Device.id == ident.device_id).first()

        acq, _ = ExtractionOrchestrator().run_acquisition(
            db,
            session_manager.require_engine(),
            case_id=case.id,
            device=device,
            examiner=examiner,
            categories=[ExtractionCategory.DEVICE_INFO, ExtractionCategory.CONTACTS, ExtractionCategory.CALL_HISTORY],
        )
        assert acq.status == AcquisitionStatus.COMPLETED_WITH_WARNINGS
        tasks_by_cat = {t.category.value: t for t in acq.tasks}
        assert tasks_by_cat["device_info"].status == TaskStatus.SUPPORTED_SUCCESS
        assert tasks_by_cat["contacts"].status == TaskStatus.UNSUPPORTED
        assert tasks_by_cat["call_history"].status == TaskStatus.UNSUPPORTED
        disconnect_device(db=db, current_examiner=examiner)


def test_extraction_aborts_if_device_unresponsive(test_db):
    from app.serial.transport import SerialTransportError

    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(case_number="CASE-2026-UNRESP", title="Unresponsive Port Test", purpose="Verify abort"),
            db=db,
            current_examiner=examiner,
        )

        connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="nokia_105_lab"),
            db=db,
            current_examiner=examiner,
        )
        engine = session_manager.require_engine()
        # Simulate device being unresponsive (timeout on AT)
        engine.transport.simulate_timeout = True

        dummy_device = Device(case_id=case.id, port_name="COM1", baud_rate=115200, is_simulated=False)
        db.add(dummy_device)
        db.commit()

        with pytest.raises(SerialTransportError, match="No responsive feature phone detected on port"):
            ExtractionOrchestrator().run_acquisition(
                db,
                engine,
                case_id=case.id,
                device=dummy_device,
                examiner=examiner,
                categories=[ExtractionCategory.CALL_HISTORY],
            )
        engine.transport.simulate_timeout = False
        disconnect_device(db=db, current_examiner=examiner)

