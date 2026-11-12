"""AT Command Capability Registry and safety classification."""

from dataclasses import dataclass
from enum import Enum


class SafetyClassification(str, Enum):
    READ_ONLY = "read_only"
    CONFIG_NON_DESTRUCTIVE = "config_non_destructive"
    DESTRUCTIVE_BLOCKED = "destructive_blocked"


class DestructiveCommandBlockedError(PermissionError):
    """Raised when a destructive or write-modifying AT command is attempted."""


@dataclass(frozen=True)
class CommandSpec:
    command: str
    description: str
    purpose: str
    expected_response: str
    device_compatibility: str
    safety: SafetyClassification


COMMAND_REGISTRY: dict[str, CommandSpec] = {
    "AT": CommandSpec(
        command="AT",
        description="Modem attention check",
        purpose="Verify serial link and AT parser readiness",
        expected_response="OK",
        device_compatibility="Universal (Hayes / GSM 07.07)",
        safety=SafetyClassification.READ_ONLY,
    ),
    "ATE0": CommandSpec(
        command="ATE0",
        description="Disable command echo",
        purpose="Prevent echoed commands from polluting parsed responses",
        expected_response="OK",
        device_compatibility="Universal (Hayes)",
        safety=SafetyClassification.CONFIG_NON_DESTRUCTIVE,
    ),
    "AT+GMI": CommandSpec(
        command="AT+GMI",
        description="Request manufacturer identification",
        purpose="Device identification",
        expected_response="Manufacturer string + OK",
        device_compatibility="GSM 07.07 (Nokia, Tecno, Itel, Samsung)",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+GMM": CommandSpec(
        command="AT+GMM",
        description="Request model identification",
        purpose="Device identification",
        expected_response="Model string + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+GMR": CommandSpec(
        command="AT+GMR",
        description="Request firmware revision",
        purpose="Firmware identification",
        expected_response="Revision string + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+GSN": CommandSpec(
        command="AT+GSN",
        description="Request product serial number / IMEI",
        purpose="IMEI acquisition",
        expected_response="15-digit IMEI + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+CGSN": CommandSpec(
        command="AT+CGSN",
        description="Request IMEI (extended)",
        purpose="IMEI acquisition fallback",
        expected_response="15-digit IMEI + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+CPIN?": CommandSpec(
        command="AT+CPIN?",
        description="Query SIM PIN status",
        purpose="Check whether SIM is READY or PIN-locked without bypassing security",
        expected_response="+CPIN: READY / SIM PIN + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+CSCS": CommandSpec(
        command="AT+CSCS",
        description="Query or select TE character set",
        purpose="Determine/configure non-destructive text encoding (GSM/UCS2/UTF-8)",
        expected_response="+CSCS: ... + OK",
        device_compatibility="GSM 07.07",
        safety=SafetyClassification.CONFIG_NON_DESTRUCTIVE,
    ),
    "AT+CPBS": CommandSpec(
        command="AT+CPBS",
        description="Phonebook memory storage selection/query",
        purpose="Inspect supported phonebook/call-log storages (SM, ME, MC, RC, DC)",
        expected_response="+CPBS: ... + OK",
        device_compatibility="GSM 07.07 (device-dependent storages)",
        safety=SafetyClassification.CONFIG_NON_DESTRUCTIVE,
    ),
    "AT+CPBR": CommandSpec(
        command="AT+CPBR",
        description="Read phonebook / call-log entries",
        purpose="Extract contacts or phonebook-style call history",
        expected_response="+CPBR: index,number,type,text + OK",
        device_compatibility="GSM 07.07 (optional on some feature phones)",
        safety=SafetyClassification.READ_ONLY,
    ),
    "AT+CPMS": CommandSpec(
        command="AT+CPMS",
        description="Preferred SMS message storage query/selection",
        purpose="Inspect SMS capacity and select SM/ME storage for reading",
        expected_response="+CPMS: ... + OK",
        device_compatibility="GSM 07.05",
        safety=SafetyClassification.CONFIG_NON_DESTRUCTIVE,
    ),
    "AT+CMGF": CommandSpec(
        command="AT+CMGF",
        description="SMS message format (0=PDU, 1=Text)",
        purpose="Query or set read format for SMS extraction",
        expected_response="+CMGF: (0,1) + OK",
        device_compatibility="GSM 07.05",
        safety=SafetyClassification.CONFIG_NON_DESTRUCTIVE,
    ),
    "AT+CMGL": CommandSpec(
        command="AT+CMGL",
        description="List SMS messages",
        purpose="Extract stored SMS messages in text or PDU mode",
        expected_response="+CMGL: ... + OK",
        device_compatibility="GSM 07.05",
        safety=SafetyClassification.READ_ONLY,
    ),
}

# Explicit blocklist of destructive / write-modifying AT command prefixes
BLOCKED_COMMAND_PREFIXES: tuple[str, ...] = (
    "AT+CMGD",   # Delete SMS
    "AT+CMGW",   # Write SMS to memory
    "AT+CMGS",   # Send SMS
    "AT+CPBW",   # Write/delete phonebook entry
    "AT+CLCK",   # Facility lock modification
    "AT+CPWD",   # Change password
    "AT+CFUN",   # Reset / power state change
    "AT&F",      # Factory reset
    "ATZ",       # Soft reset
    "ATD",       # Dial call
    "ATA",       # Answer call
    "ATH",       # Hang up
)


def normalize_command_key(raw_cmd: str) -> str:
    """Extract canonical prefix for registry lookup (e.g., 'AT+CPBR=1,50' -> 'AT+CPBR')."""
    cmd = raw_cmd.strip().upper()
    if "=" in cmd:
        return cmd.split("=", 1)[0]
    return cmd


def validate_command_safety(raw_cmd: str) -> SafetyClassification:
    """Ensure no destructive AT command is ever transmitted during forensic acquisition."""
    cmd = raw_cmd.strip().upper()
    for blocked in BLOCKED_COMMAND_PREFIXES:
        if cmd.startswith(blocked):
            raise DestructiveCommandBlockedError(
                f"Blocked destructive/non-read-only AT command: {raw_cmd!r}"
            )

    key = normalize_command_key(cmd)
    spec = COMMAND_REGISTRY.get(key)
    if spec is None:
        # Unknown commands are not blocked outright if read-query, but any '=' write requires explicit allowlist
        if "=" in cmd and not cmd.endswith("=?"):
            raise DestructiveCommandBlockedError(
                f"Unregistered state-changing AT command blocked: {raw_cmd!r}"
            )
        return SafetyClassification.READ_ONLY

    if spec.safety == SafetyClassification.DESTRUCTIVE_BLOCKED:
        raise DestructiveCommandBlockedError(f"Blocked AT command: {raw_cmd!r}")
    return spec.safety

