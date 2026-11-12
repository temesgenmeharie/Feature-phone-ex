"""Phase 9 tests: forensic analysis filtering/pagination and PDF/CSV/JSON reporting."""

from pathlib import Path

from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_examiner
from app.api.routes.acquisitions import AcquisitionCreate, start_acquisition
from app.api.routes.analysis import (
    dashboard_summary,
    get_call_records,
    get_contacts,
    get_sim_summary,
    get_sms_messages,
)
from app.api.routes.auth import login
from app.api.routes.cases import create_case
from app.api.routes.devices import ConnectRequest, IdentifyRequest, connect_device, disconnect_device, identify_device
from app.api.routes.reports import create_pdf_report, export_csv, export_json
from app.extraction.interfaces import ExtractionCategory
from app.models.forensics import CallType, EvidenceFile
from app.schemas import CaseCreate, LoginRequest
from app.serial.ports import SIMULATOR_PORT_NAME


def test_analysis_queries_and_report_exports(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )
        case = create_case(
            CaseCreate(case_number="CASE-2026-009", title="Analysis & Reporting", purpose="Verify PDF/CSV/JSON"),
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
            AcquisitionCreate(case_id=case.id, device_id=ident.device_id, categories=list(ExtractionCategory)),
            db=db,
            current_examiner=examiner,
        )
        disconnect_device(db=db, current_examiner=examiner)

        # Analysis queries
        dash = dashboard_summary(db=db, _=examiner)
        assert dash["total_cases"] == 1
        assert dash["completed_acquisitions"] == 1

        contacts = get_contacts(acq.id, search="Abebe", storage="SM", limit=50, offset=0, db=db, _=examiner)
        assert contacts.total == 1

        sms = get_sms_messages(acq.id, search="Room 204", storage=None, status_filter=None, date_from=None, date_to=None, limit=50, offset=0, db=db, _=examiner)
        assert sms.total == 1

        missed = get_call_records(acq.id, call_type=CallType.MISSED, search=None, limit=50, offset=0, db=db, _=examiner)
        assert missed.total == 2

        sim = get_sim_summary(acq.id, db=db, _=examiner)
        assert sim["sim_contacts_count"] == 2

        # PDF report + CSV + JSON export
        pdf_out = create_pdf_report(acq.id, db=db, current_examiner=examiner)
        assert pdf_out.file_name.endswith(".pdf")
        assert len(pdf_out.sha256) == 64
        pdf_row = db.query(EvidenceFile).filter(EvidenceFile.id == pdf_out.evidence_file_id).first()
        assert Path(pdf_row.file_path).read_bytes().startswith(b"%PDF-")

        csv_out = export_csv(acq.id, db=db, current_examiner=examiner)
        assert csv_out.file_name.endswith(".csv")
        json_out = export_json(acq.id, db=db, current_examiner=examiner)
        assert json_out.file_name.endswith(".json")
