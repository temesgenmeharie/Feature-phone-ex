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
    error_detail: str | None = None


def _extract_quoted_tokens(line: str) -> list[str]:
    return re.findall(r'"([A-Za-z0-9_]+)"', line)


class DeviceIdentifier:
    """Identifies device metadata and probes AT command capabilities without modifying device state."""

    def identify_and_probe(self, engine: ATCommandEngine) -> DeviceIdentificationResult:
        res = DeviceIdentificationResult(at_ready=False)

        # 1. Disable echo if supported (non-destructive)
        try:
            ate0 = engine.send_command("ATE0", timeout_s=1.5)
            res.raw_responses["ATE0"] = ate0.raw_response
        except Exception:
            pass

        # 2. Critical AT handshake
        at_check = engine.send_command("AT", timeout_s=2.0)
        res.raw_responses["AT"] = at_check.raw_response
        res.at_ready = at_check.is_ok

        if not at_check.is_ok:
            res.unsupported_commands.append("AT")
            res.error_detail = (
                f"No feature phone responded to AT commands on {engine.transport.port_name}. "
                "Ensure the phone is powered on, connected with a data USB cable, and set to 'COM Port / Modem / PC Suite' mode."
            )
            # Stop immediately without querying commands that will only timeout
            res.capabilities = {
                cat.value: {
                    "status": "unsupported",
                    "supported_commands": [],
                    "unsupported_commands": ["AT"],
                    "notes": res.error_detail,
                }
                for cat in ExtractionCategory
            }
            return res

        def query_chain(cmds: tuple[str, ...]) -> str | None:
            """Try commands in order until one returns a non-empty answer with OK."""
            for cmd in cmds:
                r = engine.send_command(cmd, timeout_s=2.0)
                res.raw_responses[cmd] = r.raw_response
                if r.is_ok and r.body_lines:
                    first = r.body_lines[0].strip()
                    if first:
                        return first
                if not r.is_ok:
                    res.unsupported_commands.append(cmd)
            return None

        # 3. Retrieve real device manufacturer, model, revision, and IMEI
        res.manufacturer = query_chain(("AT+GMI", "AT+CGMI", "ATI"))
        res.model = query_chain(("AT+GMM", "AT+CGMM", "ATI"))
        res.firmware_revision = query_chain(("AT+GMR", "AT+CGMR"))
        res.imei = query_chain(("AT+GSN", "AT+CGSN"))

        # SIM PIN status
        cpin_res = engine.send_command("AT+CPIN?", timeout_s=2.0)
        res.raw_responses["AT+CPIN?"] = cpin_res.raw_response
        if cpin_res.is_ok and cpin_res.body_lines:
            line = cpin_res.body_lines[0]
            if "+CPIN:" in line:
                res.sim_status = line.split(":", 1)[1].strip()

        # TE character set
        cscs_res = engine.send_command("AT+CSCS?", timeout_s=2.0)
        res.raw_responses["AT+CSCS?"] = cscs_res.raw_response
        if cscs_res.is_ok and cscs_res.body_lines:
            line = cscs_res.body_lines[0]
            if "+CSCS:" in line:
                tokens = _extract_quoted_tokens(line)
                res.charset = tokens[0] if tokens else line.split(":", 1)[1].strip()

        # Probe Phonebook & Call-Log storages
        cpbs_test = engine.send_command("AT+CPBS=?", timeout_s=2.5)
        res.raw_responses["AT+CPBS=?"] = cpbs_test.raw_response
        if cpbs_test.is_ok and cpbs_test.body_lines:
            res.supported_cpbs_storages = _extract_quoted_tokens(cpbs_test.body_lines[0])
        else:
            res.unsupported_commands.append("AT+CPBS=?")

        # Probe SMS storages & modes
        cpms_test = engine.send_command("AT+CPMS=?", timeout_s=2.5)
        res.raw_responses["AT+CPMS=?"] = cpms_test.raw_response
        if cpms_test.is_ok and cpms_test.body_lines:
            first_group = cpms_test.body_lines[0].split("),")[0]
            res.supported_cpms_storages = _extract_quoted_tokens(first_group)
        else:
            res.unsupported_commands.append("AT+CPMS=?")

        cmgf_test = engine.send_command("AT+CMGF=?", timeout_s=2.0)
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
