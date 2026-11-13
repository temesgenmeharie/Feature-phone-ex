"""Serial port detection for Windows COM ports, Linux serial devices, and simulator."""

from dataclasses import dataclass
import os
import re
from serial.tools import list_ports


SIMULATOR_PORT_NAME = "SIM://FEATURE_PHONE_01"


@dataclass(frozen=True)
class PortInfo:
    port_name: str
    description: str
    hwid: str
    is_simulated: bool = False
    is_usb: bool = False
    port_type: str = "other"  # "usb_phone" | "motherboard" | "simulator" | "other"


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


def _classify_port(port_name: str, desc: str, hwid: str) -> tuple[str, bool, str]:
    """Classify port into (clean_description, is_usb, port_type)."""
    hwid_upper = (hwid or "").upper()
    desc_upper = (desc or "").upper()

    # Check for motherboard/legacy onboard UART (e.g., ACPI\PNP0501)
    if "PNP0501" in hwid_upper or "ACPI\\" in hwid_upper:
        clean_desc = f"{port_name} — Motherboard Serial Port (No Phone Attached)"
        return clean_desc, False, "motherboard"

    # Check for USB Phone / Modem
    is_usb = bool(
        "USB" in hwid_upper
        or "VID:" in hwid_upper
        or "PID:" in hwid_upper
        or re.search(r"VID_[0-9A-F]{4}", hwid_upper)
        or any(k in desc_upper for k in ("MODEM", "USB", "NOKIA", "TECNO", "ITEL", "SAMSUNG", "MEDIATEK", "SPREADTRUM", "UNISOC", "VCOM"))
    )

    if is_usb:
        clean_desc = f"{port_name} — USB Phone / Modem ({desc})"
        return clean_desc, True, "usb_phone"

    return f"{port_name} — {desc}", False, "other"


def list_available_ports(include_simulator: bool = True) -> list[PortInfo]:
    """Enumerate physical serial/COM ports and optionally the built-in simulated feature phone."""
    ports: list[PortInfo] = []
    seen: set[str] = set()

    for p in list_ports.comports():
        seen.add(p.device.upper())
        desc, is_usb, port_type = _classify_port(p.device, p.description or "Serial Port", p.hwid or "")
        ports.append(
            PortInfo(
                port_name=p.device,
                description=desc,
                hwid=p.hwid or "n/a",
                is_simulated=False,
                is_usb=is_usb,
                port_type=port_type,
            )
        )

    for dev_name, reg_label in _windows_registry_serial_ports():
        if dev_name.upper() not in seen:
            seen.add(dev_name.upper())
            desc, is_usb, port_type = _classify_port(dev_name, f"Serial Device ({reg_label})", "")
            ports.append(
                PortInfo(
                    port_name=dev_name,
                    description=desc,
                    hwid="WINREG-SERIALCOMM",
                    is_simulated=False,
                    is_usb=is_usb,
                    port_type=port_type,
                )
            )

    if include_simulator:
        ports.append(
            PortInfo(
                port_name=SIMULATOR_PORT_NAME,
                description="Simulated Feature Phone (AT Lab Emulator)",
                hwid="SIMULATED-AT-MODEM-V1",
                is_simulated=True,
                is_usb=False,
                port_type="simulator",
            )
        )
    return ports
