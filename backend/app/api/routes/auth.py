"""Authentication and examiner management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner, require_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.forensics import Examiner
from app.schemas import ExaminerCreate, ExaminerOut, LoginRequest, TokenResponse
from app.services.audit_service import record_audit_event

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    examiner = db.query(Examiner).filter(Examiner.username == payload.username).first()
    if not examiner or not verify_password(payload.password, examiner.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not examiner.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Examiner account is disabled")

    token = create_access_token(subject=examiner.username, role=examiner.role.value)
    record_audit_event(db, "LOGIN", examiner_id=examiner.id, details={"username": examiner.username})
    return TokenResponse(access_token=token, examiner=ExaminerOut.model_validate(examiner))


@router.get("/auth/me", response_model=ExaminerOut)
def get_me(current_examiner: Examiner = Depends(get_current_examiner)) -> ExaminerOut:
    return ExaminerOut.model_validate(current_examiner)


@router.post("/examiners", response_model=ExaminerOut, status_code=status.HTTP_201_CREATED)
def create_examiner(
    payload: ExaminerCreate,
    db: Session = Depends(get_db),
    admin: Examiner = Depends(require_admin),
) -> ExaminerOut:
    if db.query(Examiner).filter(Examiner.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    examiner = Examiner(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(examiner)
    db.commit()
    db.refresh(examiner)
    record_audit_event(
        db,
        "EXAMINER_CREATED",
        examiner_id=admin.id,
        details={"created_username": examiner.username, "role": examiner.role.value},
    )
    return ExaminerOut.model_validate(examiner)


@router.get("/examiners", response_model=list[ExaminerOut])
def list_examiners(
    db: Session = Depends(get_db),
    _: Examiner = Depends(require_admin),
) -> list[ExaminerOut]:
    examiners = db.query(Examiner).order_by(Examiner.id.asc()).all()
    return [ExaminerOut.model_validate(e) for e in examiners]

