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
    (r"VID_0E8D&PID_0023", "MediaTek USB Modem / VCOM Port", "MediaTek"),
    (r"VID_0E8D", "MediaTek USB Feature Phone", "MediaTek"),
    # Spreadtrum / UNISOC
    (r"VID_1782&PID_4D00", "Spreadtrum USB Serial Port", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D01", "Spreadtrum USB Mass Storage (H-MOBILE)", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D02", "Spreadtrum AT Command Port", "Spreadtrum (UNISOC)"),
    (r"VID_1782&PID_4D03", "Spreadtrum Diag Port", "Spreadtrum (UNISOC)"),
    (r"VID_1782", "Spreadtrum / UNISOC USB Feature Phone", "Spreadtrum (UNISOC)"),
    # Qualcomm
    (r"VID_05C6&PID_9008", "Qualcomm HS-USB QDLoader", "Qualcomm"),
    (r"VID_05C6&PID_9091", "Qualcomm HS-USB Diagnostics / Modem", "Qualcomm"),
    (r"VID_05C6", "Qualcomm USB Handset", "Qualcomm"),
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
    """Detect connected feature phones where Windows failed to attach a driver (e.g. Code 28).

    Uses fast native Windows CfgMgr32 API to check live connected devices in real time (0ms overhead).
    """
    problems: list[DriverProblemDevice] = []
    if os.name != "nt":
        return problems

    try:
        import ctypes
        import winreg

        cfg = ctypes.windll.cfgmgr32
        enum_key_path = r"SYSTEM\CurrentControlSet\Enum\USB"

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, enum_key_path) as usb_key:
            num_subkeys, _, _ = winreg.QueryInfoKey(usb_key)
            for i in range(num_subkeys):
                dev_id = winreg.EnumKey(usb_key, i)
                try:
                    with winreg.OpenKey(usb_key, dev_id) as sub_key:
                        num_instances, _, _ = winreg.QueryInfoKey(sub_key)
                        for j in range(num_instances):
                            inst_id = winreg.EnumKey(sub_key, j)
                            full_id = f"USB\\{dev_id}\\{inst_id}"

                            dn = ctypes.c_ulong()
                            # CM_Locate_DevNodeW checks if device is PHYSICALLY PRESENT RIGHT NOW
                            if cfg.CM_Locate_DevNodeW(ctypes.byref(dn), full_id, 0) == 0:
                                status = ctypes.c_ulong()
                                problem = ctypes.c_ulong()
                                if cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), dn, 0) == 0:
                                    prob_code = problem.value
                                    if prob_code != 0:
                                        for pattern, name, vendor in KNOWN_PHONE_HARDWARE_IDS:
                                            if re.search(pattern, full_id, re.IGNORECASE):
                                                if prob_code == 10:
                                                    prob_desc = "Wrong serial driver bound (Code 10: Communications Port / serial.sys cannot start over USB)."
                                                    guide = (
                                                        f"{vendor} handset has Code 10 because 'Communications Port' (serial.sys) was selected instead of 'USB Serial Device' (usbser.sys). "
                                                        "Fix in Device Manager: Expand Ports (COM & LPT) -> right-click Communications Port (COM3) -> Update driver -> "
                                                        "Browse my computer -> Let me pick from a list -> Manufacturer: Microsoft -> Model: USB Serial Device."
                                                    )
                                                else:
                                                    prob_desc = f"Device driver missing or failed install (Code {prob_code})."
                                                    guide = (
                                                        f"{vendor} feature phone is in COM/Modem mode, but Windows has not bound the standard USB Serial driver (Code {prob_code}). "
                                                        "To enable COM port communication: Open Device Manager -> Right click device -> Update Driver -> Browse my computer -> Let me pick from a list -> "
                                                        "Ports (COM & LPT) -> Manufacturer: Microsoft (or Standard port types) -> Model: USB Serial Device (usbser.sys)."
                                                    )
                                                problems.append(
                                                    DriverProblemDevice(
                                                        instance_id=full_id,
                                                        hardware_id=pattern,
                                                        device_name=name,
                                                        vendor=vendor,
                                                        problem_code=prob_code,
                                                        problem_description=prob_desc,
                                                        resolution_guide=guide,
                                                    )
                                                )
                                                break
                except OSError:
                    continue
    except Exception:
        pass

    return problems


def detect_usb_connection_mode() -> USBModeReport:
    """Full comprehensive USB connection mode detection for connected phones."""
    # 1. Removable drives (U Disk mode)
    udisk_drives = detect_removable_drives()
    # Prioritize phone volume markers, or use any connected removable storage
    phone_udisks = [d for d in udisk_drives if d.is_phone_storage] or udisk_drives

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

    if driver_problems:
        prob = driver_problems[0]
        msg = (
            f"Detected {prob.vendor} handset connected in COM mode ({prob.device_name}), "
            f"but Windows could not start the COM port (Driver Code {prob.problem_code}). "
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

    return USBModeReport(
        primary_mode="NO_DEVICE",
        summary_message="No feature phone detected. Connect phone via USB cable and select 'U Disk' or 'COM Port' on the phone screen.",
        udisk_drives=udisk_drives,
        com_ports=com_ports,
        driver_problem_devices=driver_problems,
        charging_detected=False,
    )

