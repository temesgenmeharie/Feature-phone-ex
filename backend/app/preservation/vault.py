"""Forensic Evidence Vault: raw artifact preservation, SHA-256 hashing, and integrity verification."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.forensics import (
    ATCommandLog,
    Acquisition,
    EvidenceFile,
    EvidenceFileType,
    EvidenceHash,
    Examiner,
)
from app.services.audit_service import record_audit_event


def compute_sha256(file_path: Path) -> str:
    """Compute hex SHA-256 digest of a file in 64 KiB chunks."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def register_evidence_file(
    db: Session,
    *,
    case_id: int,
    acquisition_id: int,
    file_path: Path,
    file_type: EvidenceFileType,
    is_immutable: bool = True,
) -> EvidenceFile:
    """Register an evidence artifact and its SHA-256 hash in the database."""
    digest = compute_sha256(file_path)
    ev_file = EvidenceFile(
        case_id=case_id,
        acquisition_id=acquisition_id,
        file_name=file_path.name,
        file_path=str(file_path),
        file_type=file_type,
        file_size_bytes=file_path.stat().st_size,
        is_immutable=is_immutable,
    )
    db.add(ev_file)
    db.commit()
    db.refresh(ev_file)

    ev_hash = EvidenceHash(
        evidence_file_id=ev_file.id,
        algorithm="SHA-256",
        digest_hex=digest,
        computed_at=datetime.now(timezone.utc),
    )
    db.add(ev_hash)
    db.commit()
    return ev_file


def preserve_acquisition_evidence(
    db: Session,
    acquisition: Acquisition,
    raw_artifacts_by_cat: dict[str, dict[str, str]],
) -> list[EvidenceFile]:
    """Write raw AT transcripts, category responses, and SHA-256 manifest to the case directory."""
    ev_dir = Path(acquisition.evidence_dir)
    ev_dir.mkdir(parents=True, exist_ok=True)
    created_files: list[EvidenceFile] = []

    # 1. Raw AT command transcript
    at_logs = (
        db.query(ATCommandLog)
        .filter(ATCommandLog.acquisition_id == acquisition.id)
        .order_by(ATCommandLog.id.asc())
        .all()
    )
    transcript_path = ev_dir / "raw_at_transcript.log"
    transcript_lines = [
        f"[{log.executed_at.isoformat()}] CMD={log.command} | STATUS={log.terminal_status} | "
        f"DURATION_MS={log.duration_ms}\n{log.response}\n{'-' * 60}"
        for log in at_logs
    ]
    transcript_path.write_text("\n".join(transcript_lines), encoding="utf-8")
    created_files.append(
        register_evidence_file(
            db,
            case_id=acquisition.case_id,
            acquisition_id=acquisition.id,
            file_path=transcript_path,
            file_type=EvidenceFileType.RAW_AT_LOG,
            is_immutable=True,
        )
    )

    # 2. Raw responses per category
    for cat_name, artifacts in raw_artifacts_by_cat.items():
        raw_path = ev_dir / f"raw_{cat_name}.json"
        raw_path.write_text(json.dumps(artifacts, indent=2, ensure_ascii=False), encoding="utf-8")
        created_files.append(
            register_evidence_file(
                db,
                case_id=acquisition.case_id,
                acquisition_id=acquisition.id,
                file_path=raw_path,
                file_type=EvidenceFileType.RAW_RESPONSE,
                is_immutable=True,
            )
        )

    # 3. Evidence manifest (lists all raw files and their SHA-256 hashes)
    manifest_data: dict[str, Any] = {
        "acquisition_uid": acquisition.acquisition_uid,
        "case_id": acquisition.case_id,
        "device_id": acquisition.device_id,
        "examiner_id": acquisition.examiner_id,
        "extraction_method": acquisition.extraction_method,
        "started_at": acquisition.started_at.isoformat(),
        "completed_at": acquisition.completed_at.isoformat() if acquisition.completed_at else None,
        "limitations": acquisition.limitations_json or [],
        "files": [
            {
                "file_name": ef.file_name,
                "file_type": ef.file_type.value,
                "file_size_bytes": ef.file_size_bytes,
                "sha256": ef.evidence_hash.digest_hex if ef.evidence_hash else None,
            }
            for ef in created_files
        ],
    }
    manifest_path = ev_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    created_files.append(
        register_evidence_file(
            db,
            case_id=acquisition.case_id,
            acquisition_id=acquisition.id,
            file_path=manifest_path,
            file_type=EvidenceFileType.MANIFEST,
            is_immutable=True,
        )
    )
    return created_files


def verify_acquisition_evidence(
    db: Session,
    acquisition_id: int,
    examiner: Examiner,
) -> dict[str, Any]:
    """Recompute SHA-256 hashes on disk and compare with stored EvidenceHash records."""
    files = db.query(EvidenceFile).filter(EvidenceFile.acquisition_id == acquisition_id).all()
    results: list[dict[str, Any]] = []
    all_passed = True
    now = datetime.now(timezone.utc)

    for ef in files:
        if not ef.evidence_hash:
            continue
        p = Path(ef.file_path)
        if not p.exists():
            actual = None
            passed = False
        else:
            actual = compute_sha256(p)
            passed = actual == ef.evidence_hash.digest_hex

        ef.evidence_hash.last_verified_at = now
        ef.evidence_hash.last_verification_passed = passed
        if not passed:
            all_passed = False

        results.append(
            {
                "evidence_file_id": ef.id,
                "file_name": ef.file_name,
                "expected_sha256": ef.evidence_hash.digest_hex,
                "actual_sha256": actual,
                "passed": passed,
            }
        )

    db.commit()
    acq = db.query(Acquisition).filter(Acquisition.id == acquisition_id).first()
    record_audit_event(
        db,
        "HASH_VERIFIED",
        examiner_id=examiner.id,
        case_id=acq.case_id if acq else None,
        acquisition_id=acquisition_id,
        details={"all_passed": all_passed, "files_checked": len(results)},
    )
    return {
        "acquisition_id": acquisition_id,
        "all_passed": all_passed,
        "verified_at": now.isoformat(),
        "results": results,
    }
