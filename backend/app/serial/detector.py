"""Comprehensive USB connection mode detection and hardware diagnostics for feature phones.

Detects and classifies:
1. COM Port Mode (Active virtual COM port with Hayes AT support)
2. COM Port Mode - Driver Missing (Code 28 CM_PROB_FAILED_INSTALL on MediaTek/Spreadtrum CDC devices)
3. U Disk / USB Mass Storage Mode (Mounted FAT/FAT32 removable storage on feature phones)
4. ADB Mode (Android-based smart feature phones, KaiOS)
5. Charging Only Mode (USB power active, data bus un-enumerated)
"""

from dataclasses import dataclass, field
import os
import re
import string
import subprocess
from typing import Any

from app.serial.ports import list_available_ports, PortInfo


@dataclass
class UDiskDriveInfo:
    drive_letter: str
    volume_name: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    phone_vendor: str | None = None
    detected_folders: list[str] = field(default_factory=list)
    is_phone_storage: bool = False


@dataclass
class DriverProblemDevice:
    instance_id: str
    hardware_id: str
    device_name: str
    vendor: str
    problem_code: int
    problem_description: str
    resolution_guide: str


@dataclass
class USBModeReport:
    primary_mode: str  # "COM" | "UDISK" | "COM_DRIVER_MISSING" | "ADB" | "CHARGING_ONLY" | "NO_DEVICE"
    detected_vendor: str | None = None
    summary_message: str = ""
    udisk_drives: list[UDiskDriveInfo] = field(default_factory=list)
    com_ports: list[PortInfo] = field(default_factory=list)
    driver_problem_devices: list[DriverProblemDevice] = field(default_factory=list)
    adb_connected: bool = False
    charging_detected: bool = False


KNOWN_PHONE_HARDWARE_IDS = [
    # MediaTek
    (r"VID_0E8D&PID_0003", "MediaTek Feature Phone USB VCOM Port", "MediaTek"),
    (r"VID_0E8D&PID_2000", "MediaTek PreLoader USB VCOM Port", "MediaTek"),
    (r"VID_0E8D&PID_0001", "MediaTek DA USB VCOM Port", "MediaTek"),
    (r"VID_0E8D&PID_0002", "MediaTek USB Mass Storage", "MediaTek"),
    # Spreadtrum / UNISOC
    (r"VID_1782&PID_4D00", "Spreadtrum USB Serial Port", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D01", "Spreadtrum USB Mass Storage (H-MOBILE)", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D02", "Spreadtrum AT Command Port", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D03", "Spreadtrum Diag Port", "Spreadtrum (UNISOC)"),
    # Qualcomm
    (r"VID_05C6&PID_9008", "Qualcomm HS-USB QDLoader", "Qualcomm"),
    (r"VID_05C6&PID_9091", "Qualcomm HS-USB Diagnostics / Modem", "Qualcomm"),
    # Nokia
    (r"VID_0421", "Nokia Mobile Phone", "Nokia"),
]

PHONE_STORAGE_MARKERS = [
    "vCard", "vcard", "contacts", "Photos", "photos", "Audio", "audio",
    "Videos", "videos", "My Music", "System", "system", "PhoneBook",
    "SMS", "sms", "Messages", "backup", "Backup", "mocor", "MOCOR",
]


def detect_removable_drives() -> list[UDiskDriveInfo]:
    """Detect mounted removable USB drives and check if they belong to a feature phone."""
    drives: list[UDiskDriveInfo] = []
    if os.name != "nt":
        return drives

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            dtype = kernel32.GetDriveTypeW(path)
            # Type 2 is DRIVE_REMOVABLE
            if dtype == 2 and os.path.exists(path):
                buf_name = ctypes.create_unicode_buffer(261)
                buf_fs = ctypes.create_unicode_buffer(261)
                serial = ctypes.c_ulong()
                max_len = ctypes.c_ulong()
                flags = ctypes.c_ulong()
                kernel32.GetVolumeInformationW(
                    path, buf_name, 260,
                    ctypes.byref(serial), ctypes.byref(max_len), ctypes.byref(flags),
                    buf_fs, 260
                )
                
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                total_free = ctypes.c_ulonglong(0)
                kernel32.GetDiskFreeSpaceExW(
                    path, ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free)
                )

                vol_name = buf_name.value or ""
                fs_name = buf_fs.value or ""

                # Scan root directory for feature phone folder structure
                detected_folders: list[str] = []
                try:
                    for entry in os.scandir(path):
                        if entry.is_dir() and entry.name in PHONE_STORAGE_MARKERS:
                            detected_folders.append(entry.name)
                        elif entry.is_file() and entry.name.lower().endswith((".vcf", ".vmg", ".dat", ".bin", ".db", ".csv")):
                            detected_folders.append(entry.name)
                except Exception:
                    pass

                vol_upper = vol_name.upper()
                phone_vendor = None
                if "H-MOBILE" in vol_upper or "HMOBILE" in vol_upper:
                    phone_vendor = "H-MOBILE (Spreadtrum SC6531)"
                elif "MEDIATEK" in vol_upper or "MTK" in vol_upper:
                    phone_vendor = "Tecno / MediaTek Feature Phone"
                elif "NOKIA" in vol_upper:
                    phone_vendor = "Nokia Feature Phone"
                elif detected_folders:
                    phone_vendor = "Feature Phone Storage"

                is_phone = bool(phone_vendor or detected_folders or (total_bytes.value > 0 and total_bytes.value < 64 * 1024 * 1024 * 1024))

                drives.append(
                    UDiskDriveInfo(
                        drive_letter=f"{letter}:",
                        volume_name=vol_name,
                        filesystem=fs_name,
                        total_bytes=total_bytes.value,
                        free_bytes=free_bytes.value,
                        phone_vendor=phone_vendor,
                        detected_folders=detected_folders,
                        is_phone_storage=is_phone,
                    )
                )
    except Exception:
        pass

    return drives


def detect_driver_problem_devices() -> list[DriverProblemDevice]:
    """Detect connected feature phones where Windows failed to attach a driver (e.g. Code 28)."""
    problems: list[DriverProblemDevice] = []
    if os.name != "nt":
        return problems

    try:
        # Run fast PowerShell query to inspect devices in problem state
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-PnpDevice | Where-Object { $_.Problem -ne 'CM_PROB_NONE' -and $_.Status -eq 'Error' } | "
            "Select-Object InstanceId, Problem, Status, FriendlyName | ConvertTo-Csv -NoTypeInformation"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout:
            lines = [ln.strip() for ln in res.stdout.strip().splitlines() if ln.strip()]
            for ln in lines[1:]:
                # CSV parsing: "InstanceId","Problem","Status","FriendlyName"
                parts = [p.strip('"\r ') for p in ln.split(",")]
                if not parts or len(parts) < 2:
                    continue
                inst_id = parts[0]
                prob_code = int(parts[1]) if parts[1].isdigit() else 28

                for pattern, name, vendor in KNOWN_PHONE_HARDWARE_IDS:
                    if re.search(pattern, inst_id, re.IGNORECASE):
                        guide = (
                            f"{vendor} feature phone is in COM/Modem mode, but Windows does not have the USB serial driver bound (Code {prob_code}). "
                            "To enable COM port communication: Run Device Manager -> Right click device -> Update Driver -> "
                            "Browse my computer -> Let me pick from a list -> Ports (COM & LPT) -> Standard Port Types -> USB Serial Device (usbser.sys)."
                        )
                        problems.append(
                            DriverProblemDevice(
                                instance_id=inst_id,
                                hardware_id=pattern,
                                device_name=name,
                                vendor=vendor,
                                problem_code=prob_code,
                                problem_description=f"Device driver missing or failed install (Code {prob_code}).",
                                resolution_guide=guide,
                            )
                        )
                        break
    except Exception:
        pass

    return problems


def detect_usb_connection_mode() -> USBModeReport:
    """Full comprehensive USB connection mode detection for connected phones."""
    # 1. Removable drives (U Disk mode)
    udisk_drives = detect_removable_drives()
    phone_udisks = [d for d in udisk_drives if d.is_phone_storage]

    # 2. Driver problem devices (COM mode with missing driver)
    driver_problems = detect_driver_problem_devices()

    # 3. Available COM ports
    com_ports = list_available_ports(include_simulator=False)
    usb_com_ports = [p for p in com_ports if p.is_usb or p.port_type == "usb_phone"]

    # 4. Determine primary mode
    if phone_udisks:
        drv = phone_udisks[0]
        vendor = drv.phone_vendor or "Feature Phone"
        msg = (
            f"Detected {vendor} connected in U Disk (USB Storage) mode on {drv.drive_letter} "
            f"({drv.volume_name or 'Removable Drive'}, {drv.filesystem}). "
            "You can directly extract contacts, SMS, call logs, and carved/deleted data from this storage."
        )
        return USBModeReport(
            primary_mode="UDISK",
            detected_vendor=vendor,
            summary_message=msg,
            udisk_drives=udisk_drives,
            com_ports=com_ports,
            driver_problem_devices=driver_problems,
            charging_detected=True,
        )

    if usb_com_ports:
        port = usb_com_ports[0]
        msg = f"Detected feature phone COM port {port.port_name} ({port.description}). Ready for AT command extraction."
        return USBModeReport(
            primary_mode="COM",
            detected_vendor="USB Modem / AT Handset",
            summary_message=msg,
            udisk_drives=udisk_drives,
            com_ports=com_ports,
            driver_problem_devices=driver_problems,
            charging_detected=True,
        )

    if driver_problems:
        prob = driver_problems[0]
        msg = (
            f"Detected {prob.vendor} handset connected in COM mode ({prob.device_name}), "
            f"but Windows has not assigned a COM port (Driver Code {prob.problem_code}). "
            f"Resolution: {prob.resolution_guide}"
        )
        return USBModeReport(
            primary_mode="COM_DRIVER_MISSING",
            detected_vendor=prob.vendor,
            summary_message=msg,
            udisk_drives=udisk_drives,
            com_ports=com_ports,
            driver_problem_devices=driver_problems,
            charging_detected=True,
        )

    # If no phone detected, check registry for phantom USB feature phones (plugged in previously)
    from app.serial.ports import check_mass_storage_phone
    hint = check_mass_storage_phone()
    if hint:
        return USBModeReport(
            primary_mode="CHARGING_ONLY",
            detected_vendor="Feature Phone (Charging Only)",
            summary_message=(
                "Phone is connected but appears in Charging-only mode (USB data lines inactive). "
                "To extract data: Disconnect and reconnect the cable, watch the phone display, and press OK to select "
                "'U Disk' (Mass Storage) or 'COM Port' / 'Modem' / 'PC Suite'."
            ),
            udisk_drives=udisk_drives,
            com_ports=com_ports,
            driver_problem_devices=driver_problems,
            charging_detected=True,
        )

    return USBModeReport(
        primary_mode="NO_DEVICE",
        summary_message="No feature phone detected. Connect phone via USB cable and select 'U Disk' or 'COM Port' on the screen.",
        udisk_drives=udisk_drives,
        com_ports=com_ports,
        driver_problem_devices=driver_problems,
        charging_detected=False,
    )
