"""Phase 7 tests: evidence preservation, SHA-256 manifest, and tampering detection."""

from pathlib import Path

from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_examiner
from app.api.routes.acquisitions import (
    AcquisitionCreate,
    list_acquisition_evidence,
    start_acquisition,
    verify_evidence,
)
from app.api.routes.auth import login
from app.api.routes.cases import create_case
from app.api.routes.devices import ConnectRequest, IdentifyRequest, connect_device, disconnect_device, identify_device
from app.extraction.interfaces import ExtractionCategory
from app.schemas import CaseCreate, LoginRequest
from app.serial.ports import SIMULATOR_PORT_NAME


def test_evidence_preservation_and_sha256_verification(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(case_number="CASE-2026-007", title="Preservation Test", purpose="SHA-256 verification"),
            db=db,
            current_examiner=examiner,
        )

        connect_device(
            ConnectRequest(port_name=SIMULATOR_PORT_NAME, use_simulator=True, simulator_profile="nokia_105_lab"),
            db=db,
            current_examiner=examiner,
        )
        ident = identify_device(IdentifyRequest(case_id=case.id), db=db, current_examiner=examiner)

        acq = start_acquisition(
            AcquisitionCreate(
                case_id=case.id,
                device_id=ident.device_id,
                categories=[ExtractionCategory.DEVICE_INFO, ExtractionCategory.CONTACTS, ExtractionCategory.SMS],
            ),
            db=db,
            current_examiner=examiner,
        )
        disconnect_device(db=db, current_examiner=examiner)

        ev_files = list_acquisition_evidence(acq.id, db=db, _=examiner)
        names = {f.file_name for f in ev_files}
        assert "raw_at_transcript.log" in names
        assert "manifest.json" in names
        assert all(f.sha256 and len(f.sha256) == 64 for f in ev_files)

        # Verification should pass on untampered files
        verify_ok = verify_evidence(acq.id, db=db, current_examiner=examiner)
        assert verify_ok["all_passed"] is True

        # Simulate tampering with raw_at_transcript.log
        transcript = next(f for f in ev_files if f.file_name == "raw_at_transcript.log")
        Path(transcript.file_path).write_text("TAMPERED CONTENT", encoding="utf-8")

        verify_fail = verify_evidence(acq.id, db=db, current_examiner=examiner)
        assert verify_fail["all_passed"] is False
        failed_item = next(r for r in verify_fail["results"] if r["file_name"] == "raw_at_transcript.log")
        assert failed_item["passed"] is False
