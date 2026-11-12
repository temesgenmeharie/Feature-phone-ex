"""Forensic reporting and export endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.models.forensics import Acquisition, EvidenceFile, Examiner
from app.reporting.generator import export_csv_bundle, export_json_bundle, generate_pdf_report

router = APIRouter(tags=["reports"])


class GeneratedArtifactOut(BaseModel):
    evidence_file_id: int
    file_name: str
    file_type: str
    file_size_bytes: int
    sha256: str | None


def _to_out(ef: EvidenceFile) -> GeneratedArtifactOut:
    return GeneratedArtifactOut(
        evidence_file_id=ef.id,
        file_name=ef.file_name,
        file_type=ef.file_type.value,
        file_size_bytes=ef.file_size_bytes,
        sha256=ef.evidence_hash.digest_hex if ef.evidence_hash else None,
    )


@router.post("/acquisitions/{acquisition_id}/reports/pdf", response_model=GeneratedArtifactOut)
def create_pdf_report(
    acquisition_id: int,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> GeneratedArtifactOut:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    return _to_out(generate_pdf_report(db, acq, current_examiner))


@router.get("/acquisitions/{acquisition_id}/export/csv", response_model=GeneratedArtifactOut)
def export_csv(
    acquisition_id: int,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> GeneratedArtifactOut:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    return _to_out(export_csv_bundle(db, acq, current_examiner))


@router.get("/acquisitions/{acquisition_id}/export/json", response_model=GeneratedArtifactOut)
def export_json(
    acquisition_id: int,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> GeneratedArtifactOut:
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    if not acq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acquisition not found")
    return _to_out(export_json_bundle(db, acq, current_examiner))


@router.get("/evidence/{evidence_file_id}/download")
def download_evidence_file(
    evidence_file_id: int,
    db: Session = Depends(get_db),
    _: Examiner = Depends(get_current_examiner),
) -> FileResponse:
    ef = db.query(EvidenceFile).filter(EvidenceFile.id == evidence_file_id).first()
    if not ef or not Path(ef.file_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file not found")
    return FileResponse(path=ef.file_path, filename=ef.file_name)
