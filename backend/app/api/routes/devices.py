"""Device detection, connection, identification, and capability endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_examiner
from app.db.session import get_db
from app.extraction.identifier import DeviceIdentifier
from app.models.forensics import ATCommandLog, Case, Device, Examiner
from app.serial.manager import session_manager
from app.serial.ports import list_available_ports
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
    unsupported_commands: list[str]
    error_detail: str | None = None


_last_capabilities: dict[str, Any] = {}


@router.get("/ports", response_model=list[PortOut])
def get_ports(_: Examiner = Depends(get_current_examiner)) -> list[PortOut]:
    return [PortOut(**p.__dict__) for p in list_available_ports(include_simulator=True)]


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
        unsupported_commands=ident.unsupported_commands,
        error_detail=ident.error_detail,
    )


@router.get("/capabilities")
def get_capabilities(_: Examiner = Depends(get_current_examiner)) -> dict[str, Any]:
    return _last_capabilities

