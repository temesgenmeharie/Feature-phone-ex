"""Serial port detection for Windows COM ports, Linux serial devices, and simulator."""

from dataclasses import dataclass
from serial.tools import list_ports


SIMULATOR_PORT_NAME = "SIM://FEATURE_PHONE_01"


@dataclass(frozen=True)
class PortInfo:
    port_name: str
    description: str
    hwid: str
    is_simulated: bool = False


def list_available_ports(include_simulator: bool = True) -> list[PortInfo]:
    """Enumerate physical serial/COM ports and optionally the built-in simulated feature phone."""
    ports: list[PortInfo] = []
    for p in list_ports.comports():
        ports.append(
            PortInfo(
                port_name=p.device,
                description=p.description or "Serial Port",
                hwid=p.hwid or "n/a",
                is_simulated=False,
            )
        )

    if include_simulator:
        ports.append(
            PortInfo(
                port_name=SIMULATOR_PORT_NAME,
                description="Simulated Feature Phone (Nokia/Itel/Tecno Lab Emulator)",
                hwid="SIMULATED-AT-MODEM-V1",
                is_simulated=True,
            )
        )
    return ports

