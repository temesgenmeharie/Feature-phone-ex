"""Device identification and AT capability probing."""

from dataclasses import dataclass, field
import re
from typing import Any

from app.extraction.interfaces import CapabilityResult, CapabilityStatus, ExtractionCategory
from app.serial.engine import ATCommandEngine


@dataclass
class DeviceIdentificationResult:
    at_ready: bool
    manufacturer: str | None = None
    model: str | None = None
    firmware_revision: str | None = None
    imei: str | None = None
    sim_status: str | None = None
    charset: str | None = None
    supported_cpbs_storages: list[str] = field(default_factory=list)
    supported_cpms_storages: list[str] = field(default_factory=list)
    supported_sms_modes: list[int] = field(default_factory=list)
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    unsupported_commands: list[str] = field(default_factory=list)
    raw_responses: dict[str, str] = field(default_factory=dict)


def _extract_quoted_tokens(line: str) -> list[str]:
    return re.findall(r'"([A-Za-z0-9_]+)"', line)


class DeviceIdentifier:
    """Identifies device metadata and probes AT command capabilities without modifying device state."""

    def identify_and_probe(self, engine: ATCommandEngine) -> DeviceIdentificationResult:
        res = DeviceIdentificationResult(at_ready=False)

        # Disable echo if supported (non-destructive)
        ate0 = engine.send_command("ATE0")
        res.raw_responses["ATE0"] = ate0.raw_response

        at_check = engine.send_command("AT")
        res.raw_responses["AT"] = at_check.raw_response
        res.at_ready = at_check.is_ok
        if not at_check.is_ok:
            res.unsupported_commands.append("AT")

        def query_single(cmd: str) -> str | None:
            r = engine.send_command(cmd)
            res.raw_responses[cmd] = r.raw_response
            if r.is_ok and r.body_lines:
                return r.body_lines[0]
            if not r.is_ok:
                res.unsupported_commands.append(cmd)
            return None

        res.manufacturer = query_single("AT+GMI")
        res.model = query_single("AT+GMM")
        res.firmware_revision = query_single("AT+GMR")

        imei = query_single("AT+GSN")
        if imei is None:
            imei = query_single("AT+CGSN")
        res.imei = imei

        cpin = query_single("AT+CPIN?")
        if cpin and "+CPIN:" in cpin:
            res.sim_status = cpin.split(":", 1)[1].strip()

        cscs = query_single("AT+CSCS?")
        if cscs and "+CSCS:" in cscs:
            tokens = _extract_quoted_tokens(cscs)
            res.charset = tokens[0] if tokens else cscs.split(":", 1)[1].strip()

        # Probe Phonebook & Call-Log storages
        cpbs_test = engine.send_command("AT+CPBS=?")
        res.raw_responses["AT+CPBS=?"] = cpbs_test.raw_response
        if cpbs_test.is_ok and cpbs_test.body_lines:
            res.supported_cpbs_storages = _extract_quoted_tokens(cpbs_test.body_lines[0])
        else:
            res.unsupported_commands.append("AT+CPBS=?")

        # Probe SMS storages & modes
        cpms_test = engine.send_command("AT+CPMS=?")
        res.raw_responses["AT+CPMS=?"] = cpms_test.raw_response
        if cpms_test.is_ok and cpms_test.body_lines:
            # First parenthesized group lists read storages
            first_group = cpms_test.body_lines[0].split("),")[0]
            res.supported_cpms_storages = _extract_quoted_tokens(first_group)
        else:
            res.unsupported_commands.append("AT+CPMS=?")

        cmgf_test = engine.send_command("AT+CMGF=?")
        res.raw_responses["AT+CMGF=?"] = cmgf_test.raw_response
        if cmgf_test.is_ok and cmgf_test.body_lines:
            res.supported_sms_modes = [int(m) for m in re.findall(r"\b([01])\b", cmgf_test.body_lines[0])]
        else:
            res.unsupported_commands.append("AT+CMGF=?")

        # Build capability matrix
        cap_results = self._build_capabilities(res)
        res.capabilities = {
            c.category.value: {
                "status": c.status.value,
                "supported_commands": c.supported_commands,
                "unsupported_commands": c.unsupported_commands,
                "notes": c.notes,
            }
            for c in cap_results
        }
        return res

    @staticmethod
    def _build_capabilities(res: DeviceIdentificationResult) -> list[CapabilityResult]:
        # Device Info
        dev_cmds = [c for c, v in [("AT+GMI", res.manufacturer), ("AT+GMM", res.model), ("AT+GMR", res.firmware_revision), ("AT+GSN", res.imei)] if v]
        dev_unsup = [c for c in ("AT+GMI", "AT+GMM", "AT+GMR", "AT+GSN") if c not in dev_cmds]
        dev_status = CapabilityStatus.SUPPORTED if dev_cmds else CapabilityStatus.UNSUPPORTED

        # Contacts (SM / ME)
        contact_storages = [s for s in res.supported_cpbs_storages if s in ("SM", "ME")]
        contacts_cap = CapabilityResult(
            category=ExtractionCategory.CONTACTS,
            status=CapabilityStatus.SUPPORTED if contact_storages else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPBS=?", "AT+CPBR"] if contact_storages else [],
            unsupported_commands=[] if contact_storages else ["AT+CPBS=?"],
            notes=f"Available contact storages: {', '.join(contact_storages)}" if contact_storages else "Device does not expose SM/ME phonebook via AT+CPBS",
        )

        # Call History (MC / RC / DC)
        call_storages = [s for s in res.supported_cpbs_storages if s in ("MC", "RC", "DC")]
        calls_cap = CapabilityResult(
            category=ExtractionCategory.CALL_HISTORY,
            status=CapabilityStatus.SUPPORTED if call_storages else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPBS=?", "AT+CPBR"] if call_storages else [],
            unsupported_commands=[] if call_storages else ["AT+CPBS=MC/RC/DC"],
            notes=(
                f"Phonebook-style call storages: {', '.join(call_storages)} (limited call logs, not full network CDRs)"
                if call_storages
                else "Device does not expose call history via AT+CPBS"
            ),
        )

        # SMS
        sms_ok = bool(res.supported_cpms_storages) and bool(res.supported_sms_modes)
        sms_cap = CapabilityResult(
            category=ExtractionCategory.SMS,
            status=CapabilityStatus.SUPPORTED if sms_ok else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPMS=?", "AT+CMGF=?", "AT+CMGL"] if sms_ok else [],
            unsupported_commands=[] if sms_ok else ["AT+CPMS=?", "AT+CMGL"],
            notes=f"SMS storages: {', '.join(res.supported_cpms_storages)}; modes: {res.supported_sms_modes}" if sms_ok else "Device does not expose SMS storage via AT+CPMS",
        )

        # SIM Info
        sim_ok = res.sim_status is not None or "SM" in res.supported_cpbs_storages or "SM" in res.supported_cpms_storages
        sim_cap = CapabilityResult(
            category=ExtractionCategory.SIM_INFO,
            status=CapabilityStatus.SUPPORTED if sim_ok else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPIN?"] if res.sim_status else [],
            unsupported_commands=[] if res.sim_status else ["AT+CPIN?"],
            notes=f"SIM status: {res.sim_status or 'Unknown'}",
        )

        return [
            CapabilityResult(
                category=ExtractionCategory.DEVICE_INFO,
                status=dev_status,
                supported_commands=dev_cmds,
                unsupported_commands=dev_unsup,
            ),
            contacts_cap,
            sms_cap,
            calls_cap,
            sim_cap,
        ]
