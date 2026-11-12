"""Serial port detection for Windows COM ports, Linux serial devices, and simulator."""

from dataclasses import dataclass
import os
from serial.tools import list_ports


SIMULATOR_PORT_NAME = "SIM://FEATURE_PHONE_01"


@dataclass(frozen=True)
class PortInfo:
    port_name: str
    description: str
    hwid: str
    is_simulated: bool = False


def _windows_registry_serial_ports() -> list[tuple[str, str]]:
    """Query HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM for any COM ports not surfaced by SetupAPI."""
    if os.name != "nt":
        return []
    try:
        import winreg

        found: list[tuple[str, str]] = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    found.append((str(val), str(name)))
                    i += 1
                except OSError:
                    break
        return found
    except OSError:
        return []


def list_available_ports(include_simulator: bool = True) -> list[PortInfo]:
    """Enumerate physical serial/COM ports and optionally the built-in simulated feature phone."""
    ports: list[PortInfo] = []
    seen: set[str] = set()

    for p in list_ports.comports():
        seen.add(p.device.upper())
        ports.append(
            PortInfo(
                port_name=p.device,
                description=p.description or "Serial Port",
                hwid=p.hwid or "n/a",
                is_simulated=False,
            )
        )

    for dev_name, reg_label in _windows_registry_serial_ports():
        if dev_name.upper() not in seen:
            seen.add(dev_name.upper())
            ports.append(
                PortInfo(
                    port_name=dev_name,
                    description=f"Windows Serial/Modem ({reg_label})",
                    hwid="WINREG-SERIALCOMM",
                    is_simulated=False,
                )
            )

    if include_simulator:
        ports.append(
            PortInfo(
                port_name=SIMULATOR_PORT_NAME,
                description="Simulated Feature Phone (AT Lab Emulator)",
                hwid="SIMULATED-AT-MODEM-V1",
                is_simulated=True,
            )
        )
    return ports
