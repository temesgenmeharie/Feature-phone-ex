"""Modular logical extraction plugins for feature phones."""

import re

from app.extraction.interfaces import (
    CapabilityResult,
    CapabilityStatus,
    ExtractionCategory,
    ExtractionContext,
    ExtractionOutcome,
    ExtractionStatus,
    ExtractorPlugin,
)
from app.extraction.parsers import (
    parse_cmgl_pdu_lines,
    parse_cmgl_text_lines,
    parse_cpbr_lines,
    parse_cpbr_range,
)
from app.serial.engine import ATCommandEngine


def _quoted_tokens(line: str) -> list[str]:
    return re.findall(r'"([A-Za-z0-9_]+)"', line)


class DeviceInfoExtractor(ExtractorPlugin):
    category = ExtractionCategory.DEVICE_INFO

    def probe_capabilities(self, engine: ATCommandEngine) -> CapabilityResult:
        r = engine.send_command("AT")
        return CapabilityResult(
            category=self.category,
            status=CapabilityStatus.SUPPORTED if r.is_ok else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT"] if r.is_ok else [],
        )

    def extract(self, engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome:
        info: dict[str, str | None] = {}
        raw: dict[str, str] = {}
        for key, cmd in (
            ("manufacturer", "AT+GMI"),
            ("model", "AT+GMM"),
            ("firmware_revision", "AT+GMR"),
            ("imei", "AT+GSN"),
        ):
            r = engine.send_command(cmd)
            raw[cmd] = r.raw_response
            info[key] = r.body_lines[0] if r.is_ok and r.body_lines else None
        if info.get("imei") is None:
            r = engine.send_command("AT+CGSN")
            raw["AT+CGSN"] = r.raw_response
            info["imei"] = r.body_lines[0] if r.is_ok and r.body_lines else None

        status = ExtractionStatus.SUCCESS if any(info.values()) else ExtractionStatus.FAILED
        return ExtractionOutcome(category=self.category, status=status, records=[info], raw_artifacts=raw)


class ContactsExtractor(ExtractorPlugin):
    category = ExtractionCategory.CONTACTS

    def probe_capabilities(self, engine: ATCommandEngine) -> CapabilityResult:
        r = engine.send_command("AT+CPBS=?")
        if not r.is_ok or not r.body_lines:
            return CapabilityResult(category=self.category, status=CapabilityStatus.UNSUPPORTED, unsupported_commands=["AT+CPBS=?"])
        storages = [s for s in _quoted_tokens(r.body_lines[0]) if s in ("SM", "ME")]
        return CapabilityResult(
            category=self.category,
            status=CapabilityStatus.SUPPORTED if storages else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPBS=?", "AT+CPBR"] if storages else [],
        )

    def extract(self, engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome:
        raw: dict[str, str] = {}
        probe = engine.send_command("AT+CPBS=?")
        raw["AT+CPBS=?"] = probe.raw_response
        if not probe.is_ok or not probe.body_lines:
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.UNSUPPORTED,
                raw_artifacts=raw,
                limitations=["Device does not support AT+CPBS=? for phonebook enumeration."],
            )

        storages = [s for s in _quoted_tokens(probe.body_lines[0]) if s in ("SM", "ME")]
        if not storages:
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.UNSUPPORTED,
                raw_artifacts=raw,
                limitations=["No SM or ME contact storage exposed by device."],
            )

        records = []
        limitations: list[str] = []
        for storage in storages:
            sel = engine.send_command(f'AT+CPBS="{storage}"')
            raw[f"AT+CPBS={storage}"] = sel.raw_response
            if not sel.is_ok:
                limitations.append(f"Failed to select contact storage {storage}.")
                continue
            rng = engine.send_command("AT+CPBR=?")
            raw[f"AT+CPBR=?_{storage}"] = rng.raw_response
            start, end = parse_cpbr_range(rng.body_lines) if rng.is_ok else (1, 50)
            read_res = engine.send_command(f"AT+CPBR={start},{end}", timeout_s=6.0)
            raw[f"AT+CPBR_{storage}"] = read_res.raw_response
            if read_res.is_ok:
                records.extend(parse_cpbr_lines(read_res.body_lines, storage=storage))
            else:
                limitations.append(f"AT+CPBR failed on storage {storage}.")

        status = ExtractionStatus.SUCCESS if not limitations else (ExtractionStatus.PARTIAL if records else ExtractionStatus.FAILED)
        return ExtractionOutcome(
            category=self.category,
            status=status,
            records=records,
            raw_artifacts=raw,
            limitations=limitations,
        )


class SmsExtractor(ExtractorPlugin):
    category = ExtractionCategory.SMS

    def probe_capabilities(self, engine: ATCommandEngine) -> CapabilityResult:
        r = engine.send_command("AT+CPMS=?")
        if not r.is_ok:
            return CapabilityResult(category=self.category, status=CapabilityStatus.UNSUPPORTED, unsupported_commands=["AT+CPMS=?"])
        return CapabilityResult(category=self.category, status=CapabilityStatus.SUPPORTED, supported_commands=["AT+CPMS=?", "AT+CMGL"])

    def extract(self, engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome:
        raw: dict[str, str] = {}
        cpms_test = engine.send_command("AT+CPMS=?")
        raw["AT+CPMS=?"] = cpms_test.raw_response
        if not cpms_test.is_ok or not cpms_test.body_lines:
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.UNSUPPORTED,
                raw_artifacts=raw,
                limitations=["Device does not support AT+CPMS=? for SMS storage."],
            )

        first_group = cpms_test.body_lines[0].split("),")[0]
        storages = _quoted_tokens(first_group)
        if not storages:
            storages = ["SM"]

        cmgf_test = engine.send_command("AT+CMGF=?")
        raw["AT+CMGF=?"] = cmgf_test.raw_response
        modes = [int(m) for m in re.findall(r"\b([01])\b", " ".join(cmgf_test.body_lines))] if cmgf_test.is_ok else [1]
        use_text = 1 in modes
        mode_cmd = "AT+CMGF=1" if use_text else "AT+CMGF=0"
        mode_res = engine.send_command(mode_cmd)
        raw[mode_cmd] = mode_res.raw_response

        records = []
        limitations: list[str] = [
            "Logical SMS extraction only accesses messages exposed by AT+CMGL and cannot recover deleted SMS."
        ]
        for storage in storages:
            sel = engine.send_command(f'AT+CPMS="{storage}"')
            raw[f"AT+CPMS={storage}"] = sel.raw_response
            if not sel.is_ok:
                limitations.append(f"Could not select SMS storage {storage}.")
                continue
            list_cmd = 'AT+CMGL="ALL"' if use_text else "AT+CMGL=4"
            res = engine.send_command(list_cmd, timeout_s=8.0)
            raw[f"AT+CMGL_{storage}"] = res.raw_response
            if res.is_ok:
                if use_text:
                    records.extend(parse_cmgl_text_lines(res.body_lines, storage=storage))
                else:
                    records.extend(parse_cmgl_pdu_lines(res.body_lines, storage=storage))
            else:
                limitations.append(f"AT+CMGL failed on SMS storage {storage}.")

        return ExtractionOutcome(
            category=self.category,
            status=ExtractionStatus.SUCCESS,
            records=records,
            raw_artifacts=raw,
            limitations=limitations,
        )


class CallHistoryExtractor(ExtractorPlugin):
    category = ExtractionCategory.CALL_HISTORY

    STORAGE_TO_CALL_TYPE = {"MC": "missed", "RC": "received", "DC": "dialed"}

    def probe_capabilities(self, engine: ATCommandEngine) -> CapabilityResult:
        r = engine.send_command("AT+CPBS=?")
        if not r.is_ok or not r.body_lines:
            return CapabilityResult(category=self.category, status=CapabilityStatus.UNSUPPORTED, unsupported_commands=["AT+CPBS=?"])
        storages = [s for s in _quoted_tokens(r.body_lines[0]) if s in self.STORAGE_TO_CALL_TYPE]
        return CapabilityResult(
            category=self.category,
            status=CapabilityStatus.SUPPORTED if storages else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPBS", "AT+CPBR"] if storages else [],
        )

    def extract(self, engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome:
        raw: dict[str, str] = {}
        probe = engine.send_command("AT+CPBS=?")
        raw["AT+CPBS=?"] = probe.raw_response
        if not probe.is_ok or not probe.body_lines:
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.UNSUPPORTED,
                raw_artifacts=raw,
                limitations=["Device does not support AT+CPBS=? for call-log extraction."],
            )

        storages = [s for s in _quoted_tokens(probe.body_lines[0]) if s in self.STORAGE_TO_CALL_TYPE]
        if not storages:
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.UNSUPPORTED,
                raw_artifacts=raw,
                limitations=["Device does not expose MC/RC/DC call-log storages over AT commands."],
            )

        records = []
        limitations = [
            "Extracted call records originate from phonebook-style AT+CPBR call logs (MC/RC/DC), "
            "not carrier/network CDRs; timestamps and call durations are unavailable unless exposed by firmware."
        ]
        for storage in storages:
            sel = engine.send_command(f'AT+CPBS="{storage}"')
            raw[f"AT+CPBS={storage}"] = sel.raw_response
            if not sel.is_ok:
                limitations.append(f"Could not select call storage {storage}.")
                continue
            rng = engine.send_command("AT+CPBR=?")
            start, end = parse_cpbr_range(rng.body_lines) if rng.is_ok else (1, 50)
            read_res = engine.send_command(f"AT+CPBR={start},{end}", timeout_s=6.0)
            raw[f"AT+CPBR_{storage}"] = read_res.raw_response
            if read_res.is_ok:
                for entry in parse_cpbr_lines(read_res.body_lines, storage=storage):
                    records.append(
                        {
                            "call_type": self.STORAGE_TO_CALL_TYPE[storage],
                            "record_index": entry["record_index"],
                            "phone_number": entry["phone_number"],
                            "contact_name": entry["name"],
                            "timestamp_raw": None,
                            "timestamp_iso": None,
                            "duration_seconds": None,
                            "storage_location": storage,
                            "is_cdr_level": False,
                            "raw_entry": entry["raw_entry"],
                        }
                    )

        return ExtractionOutcome(
            category=self.category,
            status=ExtractionStatus.SUCCESS,
            records=records,
            raw_artifacts=raw,
            limitations=limitations,
        )


class SimInfoExtractor(ExtractorPlugin):
    category = ExtractionCategory.SIM_INFO

    def probe_capabilities(self, engine: ATCommandEngine) -> CapabilityResult:
        r = engine.send_command("AT+CPIN?")
        return CapabilityResult(
            category=self.category,
            status=CapabilityStatus.SUPPORTED if r.is_ok else CapabilityStatus.UNSUPPORTED,
            supported_commands=["AT+CPIN?"] if r.is_ok else [],
        )

    def extract(self, engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome:
        raw: dict[str, str] = {}
        cpin = engine.send_command("AT+CPIN?")
        raw["AT+CPIN?"] = cpin.raw_response
        sim_status = cpin.body_lines[0].split(":", 1)[1].strip() if cpin.is_ok and cpin.body_lines and ":" in cpin.body_lines[0] else "Unknown"

        limitations: list[str] = []
        if "PIN" in sim_status.upper() or "PUK" in sim_status.upper():
            limitations.append(f"SIM is locked ({sim_status}); security bypass is prohibited.")
            return ExtractionOutcome(
                category=self.category,
                status=ExtractionStatus.PARTIAL,
                records=[{"sim_status": sim_status}],
                raw_artifacts=raw,
                limitations=limitations,
            )

        sim_pb = None
        if engine.send_command('AT+CPBS="SM"').is_ok:
            q = engine.send_command("AT+CPBS?")
            raw["AT+CPBS?_SM"] = q.raw_response
            if q.is_ok and q.body_lines:
                sim_pb = q.body_lines[0]

        sim_sms = None
        if engine.send_command('AT+CPMS="SM"').is_ok:
            q = engine.send_command("AT+CPMS?")
            raw["AT+CPMS?_SM"] = q.raw_response
            if q.is_ok and q.body_lines:
                sim_sms = q.body_lines[0]

        return ExtractionOutcome(
            category=self.category,
            status=ExtractionStatus.SUCCESS,
            records=[{"sim_status": sim_status, "sim_phonebook_usage": sim_pb, "sim_sms_usage": sim_sms}],
            raw_artifacts=raw,
            limitations=limitations,
        )


EXTRACTOR_REGISTRY: dict[ExtractionCategory, ExtractorPlugin] = {
    ExtractionCategory.DEVICE_INFO: DeviceInfoExtractor(),
    ExtractionCategory.CONTACTS: ContactsExtractor(),
    ExtractionCategory.SMS: SmsExtractor(),
    ExtractionCategory.CALL_HISTORY: CallHistoryExtractor(),
    ExtractionCategory.SIM_INFO: SimInfoExtractor(),
}
