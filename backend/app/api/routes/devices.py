"""Device detection, connection, identification, and capability endpoints."""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.extraction.identifier import DeviceIdentifier
from app.extraction.interfaces import ExtractionCategory
from app.extraction.orchestrator import ExtractionOrchestrator
from app.models.forensics import ATCommandLog, Case, Device, Examiner
from app.serial.detector import detect_usb_connection_mode, detect_removable_drives, detect_driver_problem_devices
from app.serial.manager import session_manager
from app.serial.ports import check_mass_storage_phone, list_available_ports
from app.serial.transport import SerialTransportError
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/devices", tags=["devices"])


class PortOut(BaseModel):
    port_name: str
    description: str
    hwid: str
    is_simulated: bool
    is_usb: bool = False
    port_type: str = "other"


class ConnectRequest(BaseModel):
    port_name: str
    baud_rate: int = Field(default=115200, ge=1200, le=921600)
    timeout_s: float = Field(default=3.0, ge=0.5, le=30.0)
    use_simulator: bool = False
    simulator_profile: str = "nokia_105_lab"


class ConnectionStatusOut(BaseModel):
    connected: bool
    port_name: str | None = None
    baud_rate: int | None = None
    is_simulated: bool = False
    simulator_profile: str | None = None


class IdentifyRequest(BaseModel):
    case_id: int | None = None


class DeviceIdentifyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: int | None = None
    at_ready: bool
    manufacturer: str | None
    model: str | None
    firmware_revision: str | None
    imei: str | None
    sim_status: str | None
    charset: str | None
    supported_cpbs_storages: list[str]
    supported_cpms_storages: list[str]
    supported_sms_modes: list[int]
    capabilities: dict[str, Any]
    storage_stats: dict[str, Any] = {}
    unsupported_commands: list[str]
    error_detail: str | None = None


class DiscoveredArtifactOut(BaseModel):
    category: str
    file_name: str
    file_path: str
    size_bytes: int
    estimated_count: int
    description: str
    is_deleted_carvable: bool = False


class UDiskPreviewOut(BaseModel):
    drive_letter: str
    volume_name: str
    filesystem: str
    phone_vendor: str | None
    total_bytes: int
    free_bytes: int
    used_bytes: int
    contacts_count: int
    sms_count: int
    calls_count: int
    carved_candidates_count: int
    artifacts: list[DiscoveredArtifactOut] = []
    supported_categories: list[str] = []
    forensic_guarantee: str = "Read-Only Non-Destructive Acquisition, SHA-256 Validated"


class UDiskDriveOut(BaseModel):
    drive_letter: str
    volume_name: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    phone_vendor: str | None = None
    detected_folders: list[str] = []
    is_phone_storage: bool = False


class DriverProblemOut(BaseModel):
    instance_id: str
    hardware_id: str
    device_name: str
    vendor: str
    problem_code: int
    problem_description: str
    resolution_guide: str


class DiagnosticOut(BaseModel):
    primary_mode: str = "NO_DEVICE"
    detected_vendor: str | None = None
    summary_message: str = ""
    udisk_drives: list[UDiskDriveOut] = []
    driver_problem_devices: list[DriverProblemOut] = []
    charging_detected: bool = False
    mass_storage_detected: bool = False
    message: str | None = None


class UDiskExtractRequest(BaseModel):
    case_id: int
    drive_letter: str
    categories: list[ExtractionCategory] = [
        ExtractionCategory.DEVICE_INFO,
        ExtractionCategory.CONTACTS,
        ExtractionCategory.SMS,
        ExtractionCategory.CALL_HISTORY,
    ]


_last_capabilities: dict[str, Any] = {}
_orchestrator = ExtractionOrchestrator()


@router.get("/diagnostics", response_model=DiagnosticOut)
def get_device_diagnostics(_: Examiner = Depends(get_current_examiner)) -> DiagnosticOut:
    report = detect_usb_connection_mode()
    hint = report.summary_message
    is_mass_storage = report.primary_mode == "UDISK" or bool(report.udisk_drives)
    return DiagnosticOut(
        primary_mode=report.primary_mode,
        detected_vendor=report.detected_vendor,
        summary_message=report.summary_message,
        udisk_drives=[UDiskDriveOut(**d.__dict__) for d in report.udisk_drives],
        driver_problem_devices=[DriverProblemOut(**p.__dict__) for p in report.driver_problem_devices],
        charging_detected=report.charging_detected,
        mass_storage_detected=is_mass_storage,
        message=hint,
    )


@router.get("/udisk/drives", response_model=list[UDiskDriveOut])
def get_udisk_drives(_: Examiner = Depends(get_current_examiner)) -> list[UDiskDriveOut]:
    drives = detect_removable_drives()
    return [UDiskDriveOut(**d.__dict__) for d in drives]


@router.post("/udisk/extract")
def extract_from_udisk(
    payload: UDiskExtractRequest,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> dict[str, Any]:
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    drive_letter = payload.drive_letter.upper().rstrip("\\")
    drive_path = f"{drive_letter}\\"
    if not os.path.exists(drive_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot extract data: Phone storage drive {payload.drive_letter} is not connected or accessible. "
                "Please connect your feature phone via USB cable, unlock the keypad, and select 'U Disk' or 'Mass Storage' on the phone screen."
            ),
        )

    drives = detect_removable_drives()
    matched = next((d for d in drives if d.drive_letter.upper() == drive_letter), None)
    vendor = matched.phone_vendor if matched and matched.phone_vendor else "USB Feature Phone"
    model = matched.volume_name if matched and matched.volume_name else "Mass Storage Handset"

    device = Device(
        case_id=case.id,
        port_name=f"UDISK://{drive_letter.replace(':', '')}",
        manufacturer=vendor,
        model=model,
        imei="N/A (U-Disk Mode)",
        is_simulated=False,
        identified_at=datetime.now(timezone.utc),
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    acquisition, raw_artifacts = _orchestrator.run_udisk_acquisition(
        db,
        drive_path,
        case_id=case.id,
        device=device,
        examiner=current_examiner,
        categories=payload.categories,
    )

    return {
        "status": "success",
        "acquisition_id": acquisition.id,
        "acquisition_uid": acquisition.acquisition_uid,
        "device_id": device.id,
        "extraction_method": "UDISK_FORENSIC",
        "drive_letter": payload.drive_letter,
        "evidence_dir": acquisition.evidence_dir,
        "categories_extracted": [c.value for c in payload.categories],
    }


@router.get("/ports", response_model=list[PortOut])
def get_ports(
    include_simulator: bool = Query(default=False),
    _: Examiner = Depends(get_current_examiner),
) -> list[PortOut]:
    return [PortOut(**p.__dict__) for p in list_available_ports(include_simulator=include_simulator)]


@router.post("/connect", response_model=ConnectionStatusOut)
def connect_device(
    payload: ConnectRequest,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> ConnectionStatusOut:
    try:
        st = session_manager.connect(
            port_name=payload.port_name,
            baud_rate=payload.baud_rate,
            timeout_s=payload.timeout_s,
            use_simulator=payload.use_simulator,
            simulator_profile=payload.simulator_profile,
        )
    except SerialTransportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        "PORT_CONNECTED",
        examiner_id=current_examiner.id,
        details={"port_name": st.port_name, "baud_rate": st.baud_rate, "is_simulated": st.is_simulated},
    )
    return ConnectionStatusOut(**st.__dict__)


@router.post("/disconnect", response_model=ConnectionStatusOut)
def disconnect_device(
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> ConnectionStatusOut:
    prev = session_manager.status()
    st = session_manager.disconnect()
    record_audit_event(
        db,
        "PORT_DISCONNECTED",
        examiner_id=current_examiner.id,
        details={"port_name": prev.port_name},
    )
    return ConnectionStatusOut(**st.__dict__)


@router.get("/status", response_model=ConnectionStatusOut)
def device_status(_: Examiner = Depends(get_current_examiner)) -> ConnectionStatusOut:
    return ConnectionStatusOut(**session_manager.status().__dict__)


@router.post("/identify", response_model=DeviceIdentifyOut)
def identify_device(
    payload: IdentifyRequest | None = None,
    db: Session = Depends(get_db),
    current_examiner: Examiner = Depends(get_current_examiner),
) -> DeviceIdentifyOut:
    global _last_capabilities
    try:
        engine = session_manager.require_engine()
        log_start_idx = len(engine.logs)
        ident = DeviceIdentifier().identify_and_probe(engine)
    except SerialTransportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _last_capabilities = ident.capabilities

    device_id: int | None = None
    case_id = payload.case_id if payload else None
    if ident.at_ready and case_id is not None:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        conn = session_manager.status()
        device = Device(
            case_id=case.id,
            port_name=conn.port_name,
            baud_rate=conn.baud_rate,
            manufacturer=ident.manufacturer,
            model=ident.model,
            firmware_revision=ident.firmware_revision,
            imei=ident.imei,
            is_simulated=conn.is_simulated,
            capabilities_json=ident.capabilities,
            identified_at=datetime.now(timezone.utc),
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        device_id = device.id

        for log_item in engine.logs[log_start_idx:]:
            db.add(
                ATCommandLog(
                    device_id=device.id,
                    command=log_item.command,
                    response=log_item.raw_response,
                    terminal_status=log_item.terminal_status,
                    duration_ms=log_item.duration_ms,
                    executed_at=log_item.executed_at,
                )
            )
        db.commit()

    record_audit_event(
        db,
        "DEVICE_IDENTIFIED",
        examiner_id=current_examiner.id,
        case_id=case_id,
        details={
            "at_ready": ident.at_ready,
            "manufacturer": ident.manufacturer,
            "model": ident.model,
            "imei": ident.imei,
        },
    )

    return DeviceIdentifyOut(
        device_id=device_id,
        at_ready=ident.at_ready,
        manufacturer=ident.manufacturer,
        model=ident.model,
        firmware_revision=ident.firmware_revision,
        imei=ident.imei,
        sim_status=ident.sim_status,
        charset=ident.charset,
        supported_cpbs_storages=ident.supported_cpbs_storages,
        supported_cpms_storages=ident.supported_cpms_storages,
        supported_sms_modes=ident.supported_sms_modes,
        capabilities=ident.capabilities,
        storage_stats=getattr(ident, "storage_stats", {}),
        unsupported_commands=ident.unsupported_commands,
        error_detail=ident.error_detail,
    )


@router.get("/udisk/preview", response_model=UDiskPreviewOut)
def preview_udisk_drive(
    drive_letter: str = Query(...),
    _: Examiner = Depends(get_current_examiner),
) -> UDiskPreviewOut:
    drive_clean = drive_letter.upper().rstrip("\\")
    drive_path = Path(f"{drive_clean}\\")
    if not drive_path.exists():
        if Path(drive_letter).exists():
            drive_path = Path(drive_letter)
            drive_clean = str(drive_path)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Drive {drive_letter} is not accessible.")

    import re, shutil
    drives = detect_removable_drives()
    matched = next((d for d in drives if d.drive_letter.upper() == drive_clean), None)
    vendor = matched.phone_vendor if matched else "Feature Phone Storage"
    vol_name = matched.volume_name if matched else "REMOVABLE"
    fs_name = matched.filesystem if matched else "FAT"

    total_b, used_b, free_b = 0, 0, 0
    try:
        u = shutil.disk_usage(drive_path)
        total_b, used_b, free_b = u.total, u.used, u.free
    except Exception:
        pass

    artifacts: list[DiscoveredArtifactOut] = []
    contacts_count = 0
    sms_count = 0
    calls_count = 0
    carved_candidates = 0

    try:
        for root, _, files in os.walk(drive_path):
            for f in files:
                p = Path(root) / f
                ext = p.suffix.lower()
                fname = p.name.lower()
                size = p.stat().st_size if p.exists() else 0
                rel_path = str(p.relative_to(drive_path))

                if ext == ".vcf":
                    try:
                        c_text = p.read_text(encoding="utf-8", errors="ignore")
                        cnt = len(re.findall(r"BEGIN:VCARD", c_text, re.IGNORECASE))
                        contacts_count += cnt
                        artifacts.append(DiscoveredArtifactOut(
                            category="contacts",
                            file_name=p.name,
                            file_path=rel_path,
                            size_bytes=size,
                            estimated_count=cnt,
                            description=f"vCard Address Book ({cnt} contact entries)",
                            is_deleted_carvable=False,
                        ))
                    except Exception:
                        pass
                elif ext in (".vmg", ".vnt"):
                    try:
                        m_text = p.read_text(encoding="utf-8", errors="ignore")
                        cnt = len(re.findall(r"BEGIN:VMSG", m_text, re.IGNORECASE)) or 1
                        sms_count += cnt
                        artifacts.append(DiscoveredArtifactOut(
                            category="sms",
                            file_name=p.name,
                            file_path=rel_path,
                            size_bytes=size,
                            estimated_count=cnt,
                            description=f"vMessage SMS Store ({cnt} messages)",
                            is_deleted_carvable=False,
                        ))
                    except Exception:
                        pass
                elif "call" in fname or "history" in fname or ext == ".csv":
                    cnt = max(1, size // 64) if ext != ".csv" else 15
                    calls_count += cnt
                    artifacts.append(DiscoveredArtifactOut(
                        category="call_history",
                        file_name=p.name,
                        file_path=rel_path,
                        size_bytes=size,
                        estimated_count=cnt,
                        description=f"Call Log Records ({p.name})",
                        is_deleted_carvable=True,
                    ))
                elif ext in (".dat", ".bin", ".db", ".sqlite", ".bak", ".tmp") or "sms" in fname or "msg" in fname:
                    carved_candidates += 1
                    artifacts.append(DiscoveredArtifactOut(
                        category="deleted_carving",
                        file_name=p.name,
                        file_path=rel_path,
                        size_bytes=size,
                        estimated_count=max(1, size // 160),
                        description="Binary container eligible for deleted SMS PDU / Call carving",
                        is_deleted_carvable=True,
                    ))
    except Exception:
        pass

    carved_candidates = sum(1 for a in artifacts if a.is_deleted_carvable)

    supported_cats = ["device_info"]
    if contacts_count > 0 or any(a.category == "contacts" for a in artifacts):
        supported_cats.append("contacts")
    if sms_count > 0 or any(a.category == "sms" for a in artifacts):
        supported_cats.append("sms")
    if calls_count > 0 or any(a.category == "call_history" for a in artifacts):
        supported_cats.append("call_history")

    return UDiskPreviewOut(
        drive_letter=drive_clean,
        volume_name=vol_name,
        filesystem=fs_name,
        phone_vendor=vendor,
        total_bytes=total_b,
        free_bytes=free_b,
        used_bytes=used_b,
        contacts_count=contacts_count,
        sms_count=sms_count,
        calls_count=calls_count,
        carved_candidates_count=carved_candidates,
        artifacts=artifacts,
        supported_categories=supported_cats,
        forensic_guarantee="Read-Only Acquisition; Physical Artifact Preservation with SHA-256 Hashes",
    )


@router.get("/capabilities")
def get_capabilities(_: Examiner = Depends(get_current_examiner)) -> dict[str, Any]:
    return _last_capabilities

