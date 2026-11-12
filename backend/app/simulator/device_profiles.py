"""Realistic feature-phone profiles for the AT-command simulator."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimulatedContact:
    index: int
    name: str
    number: str
    num_type: int = 145  # 145 = international (+), 129 = national


@dataclass(frozen=True)
class SimulatedSms:
    index: int
    status: str  # "REC UNREAD", "REC READ", "STO UNSENT", "STO SENT"
    address: str
    timestamp: str  # e.g., "26/11/10,09:15:30+12"
    body: str
    pdu_hex: str = ""


@dataclass(frozen=True)
class SimulatedDeviceProfile:
    profile_id: str
    manufacturer: str
    model: str
    revision: str
    imei: str
    sim_status: str = "READY"
    supported_cpbs: tuple[str, ...] = ("SM", "ME", "MC", "RC", "DC")
    supported_cpms: tuple[str, ...] = ("SM", "ME")
    supports_cmgf_text: bool = True
    supports_imei: bool = True
    contacts: dict[str, list[SimulatedContact]] = field(default_factory=dict)
    call_logs: dict[str, list[SimulatedContact]] = field(default_factory=dict)
    sms_messages: dict[str, list[SimulatedSms]] = field(default_factory=dict)


def build_default_profile() -> SimulatedDeviceProfile:
    """Return a realistic Nokia-style feature phone profile for lab training."""
    return SimulatedDeviceProfile(
        profile_id="nokia_105_lab",
        manufacturer="Nokia",
        model="Nokia 105 (TA-1174)",
        revision="V 14.00.11",
        imei="358912094512345",
        sim_status="READY",
        supported_cpbs=("SM", "ME", "MC", "RC", "DC"),
        supported_cpms=("SM", "ME"),
        supports_cmgf_text=True,
        supports_imei=True,
        contacts={
            "SM": [
                SimulatedContact(1, "Abebe Kebede", "+251911223344", 145),
                SimulatedContact(2, "Tigist Alemu", "+251912334455", 145),
            ],
            "ME": [
                SimulatedContact(1, "Lab Coordinator", "+251913445566", 145),
                SimulatedContact(2, "Dispatch Desk", "0911998877", 129),
            ],
        },
        call_logs={
            "MC": [
                SimulatedContact(1, "Tigist Alemu", "+251912334455", 145),
                SimulatedContact(2, "", "+251922001122", 145),
            ],
            "RC": [
                SimulatedContact(1, "Abebe Kebede", "+251911223344", 145),
            ],
            "DC": [
                SimulatedContact(1, "Lab Coordinator", "+251913445566", 145),
                SimulatedContact(2, "Emergency Lab", "911", 129),
            ],
        },
        sms_messages={
            "SM": [
                SimulatedSms(
                    index=1,
                    status="REC READ",
                    address="+251911223344",
                    timestamp="26/11/10,08:30:12+12",
                    body="Please confirm receipt of the lab test SIM.",
                ),
            ],
            "ME": [
                SimulatedSms(
                    index=1,
                    status="REC UNREAD",
                    address="+251912334455",
                    timestamp="26/11/11,14:05:44+12",
                    body="Meeting moved to Room 204 at 15:00.",
                ),
                SimulatedSms(
                    index=2,
                    status="STO SENT",
                    address="+251913445566",
                    timestamp="26/11/11,16:20:00+12",
                    body="Device intake completed.",
                ),
            ],
        },
    )


def build_limited_modem_profile() -> SimulatedDeviceProfile:
    """Return a restricted feature-phone profile that only exposes basic modem identification."""
    return SimulatedDeviceProfile(
        profile_id="itel_limited_modem",
        manufacturer="Itel",
        model="it2160",
        revision="SW_V1.0.4",
        imei="352109887766554",
        sim_status="READY",
        supported_cpbs=(),
        supported_cpms=(),
        supports_cmgf_text=False,
        supports_imei=True,
    )


PROFILES: dict[str, SimulatedDeviceProfile] = {
    "nokia_105_lab": build_default_profile(),
    "itel_limited_modem": build_limited_modem_profile(),
}
