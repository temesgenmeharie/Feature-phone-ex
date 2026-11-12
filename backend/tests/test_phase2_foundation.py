"""Phase 2 tests: health, auth, RBAC, cases, audit logs, and ORM relationships."""

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from app.api.deps import get_current_examiner, require_admin
from app.api.routes.audit import list_audit_logs
from app.api.routes.auth import create_examiner, login
from app.api.routes.cases import create_case, list_cases, update_case
from app.api.routes.health import health_check
from app.models.forensics import CaseStatus, ExaminerRole
from app.schemas import CaseCreate, CaseUpdate, ExaminerCreate, LoginRequest


def test_health_endpoint():
    data = health_check()
    assert data.status == "ok"
    assert data.offline_mode is True


def test_login_and_rbac(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            login(LoginRequest(username="admin", password="wrong"), db=db)
        assert exc.value.status_code == 401

        admin_tok = login(LoginRequest(username="admin", password="AdminPass123!"), db=db)
        exam_tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)

        admin_user = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_tok.access_token), db=db
        )
        exam_user = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=exam_tok.access_token), db=db
        )

        # Examiner cannot pass require_admin
        with pytest.raises(HTTPException) as exc_rbac:
            require_admin(exam_user)
        assert exc_rbac.value.status_code == 403

        # Admin can create examiner
        created = create_examiner(
            ExaminerCreate(
                username="examiner2",
                full_name="Second Examiner",
                role=ExaminerRole.EXAMINER,
                password="Password123!",
            ),
            db=db,
            admin=require_admin(admin_user),
        )
        assert created.username == "examiner2"


def test_case_lifecycle_and_audit_trail(test_db):
    SessionLocal, _ = test_db
    with SessionLocal() as db:
        tok = login(LoginRequest(username="examiner1", password="ExaminerPass123!"), db=db)
        examiner = get_current_examiner(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok.access_token), db=db
        )

        case_out = create_case(
            CaseCreate(
                case_number="CASE-2026-001",
                title="Nokia 105 Lab Examination",
                purpose="Forensic training logical extraction",
                device_owner_ref="LAB-DEVICE-01",
                device_description="Nokia 105 TA-1174",
                notes="Initial intake",
            ),
            db=db,
            current_examiner=examiner,
        )
        assert case_out.case_number == "CASE-2026-001"
        assert case_out.status == CaseStatus.OPEN

        found = list_cases(status_filter=None, search="Nokia", db=db, _=examiner)
        assert len(found) == 1

        updated = update_case(
            case_out.id,
            CaseUpdate(status=CaseStatus.IN_PROGRESS, notes="Connected to lab workstation"),
            db=db,
            current_examiner=examiner,
        )
        assert updated.status == CaseStatus.IN_PROGRESS

        logs = list_audit_logs(case_id=case_out.id, acquisition_id=None, action=None, limit=100, db=db, _=examiner)
        actions = [entry.action for entry in logs]
        assert "CASE_CREATED" in actions
        assert "CASE_UPDATED" in actions
