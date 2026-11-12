"""FastAPI dependencies for authentication and role-based access control."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.forensics import Examiner, ExaminerRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_examiner(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Examiner:
    """Validate Bearer JWT and return the active Examiner."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    examiner = db.query(Examiner).filter(Examiner.username == payload["sub"]).first()
    if not examiner or not examiner.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown examiner")
    return examiner


def require_admin(current_examiner: Examiner = Depends(get_current_examiner)) -> Examiner:
    """Restrict endpoint to administrator role."""
    if current_examiner.role != ExaminerRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges required")
    return current_examiner

