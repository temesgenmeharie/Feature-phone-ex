"""Simulated SerialTransport implementing Hayes AT command responses."""

import re

from app.extraction.interfaces import SerialTransport
from app.serial.ports import SIMULATOR_PORT_NAME
from app.serial.transport import SerialTransportError
from app.simulator.device_profiles import PROFILES, SimulatedDeviceProfile, build_default_profile


class SimulatedSerialTransport(SerialTransport):
    """In-memory virtual feature phone speaking standard Hayes / GSM 07.07 / 07.05 AT commands."""

    def __init__(
        self,
        port_name: str = SIMULATOR_PORT_NAME,
        baud_rate: int = 115200,
        profile: SimulatedDeviceProfile | None = None,
    ) -> None:
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.profile = profile or build_default_profile()
        self._open = False
        self._echo = False
        self._charset = "GSM"
        self._current_cpbs = "SM"
        self._current_cpms = "SM"
        self._cmgf_mode = 1  # 1 = text, 0 = PDU
        self._response_buffer = ""

        # Fault-injection hooks for testing
        self.simulate_timeout = False
        self.simulate_disconnect = False

    @classmethod
    def from_profile_id(cls, profile_id: str, baud_rate: int = 115200) -> "SimulatedSerialTransport":
        profile = PROFILES.get(profile_id, build_default_profile())
        return cls(baud_rate=baud_rate, profile=profile)

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False
        self._response_buffer = ""

    def is_open(self) -> bool:
        return self._open

    def write(self, data: bytes) -> int:
        if not self._open or self.simulate_disconnect:
            raise SerialTransportError("Simulated device disconnected")
        cmd = data.decode("ascii", errors="ignore").strip()
        self._response_buffer = self._handle_command(cmd)
        return len(data)

    def read_until_terminal(self, terminals: tuple[str, ...], timeout_s: float) -> str:
        if not self._open or self.simulate_disconnect:
            raise SerialTransportError("Simulated device disconnected")
        if self.simulate_timeout:
            return ""
        out = self._response_buffer
        self._response_buffer = ""
        return out

    def _wrap(self, cmd: str, *lines: str, terminal: str = "OK") -> str:
        parts: list[str] = []
        if self._echo:
            parts.append(cmd)
        parts.extend(lines)
        parts.append(terminal)
        return "\r\n".join(parts) + "\r\n"

    def _handle_command(self, cmd: str) -> str:
        upper = cmd.upper()

        if upper == "AT":
            return self._wrap(cmd)
        if upper == "ATE0":
            self._echo = False
            return self._wrap(cmd)
        if upper == "ATE1":
            self._echo = True
            return self._wrap(cmd)

        if upper == "AT+GMI":
            return self._wrap(cmd, self.profile.manufacturer)
        if upper == "AT+GMM":
            return self._wrap(cmd, self.profile.model)
        if upper == "AT+GMR":
            return self._wrap(cmd, self.profile.revision)
        if upper in ("AT+GSN", "AT+CGSN"):
            if not self.profile.supports_imei:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            return self._wrap(cmd, self.profile.imei)

        if upper == "AT+CPIN?":
            return self._wrap(cmd, f"+CPIN: {self.profile.sim_status}")

        if upper == "AT+CSCS=?":
            return self._wrap(cmd, '+CSCS: ("GSM","UCS2","UTF-8")')
        if upper == "AT+CSCS?":
            return self._wrap(cmd, f'+CSCS: "{self._charset}"')
        if upper.startswith("AT+CSCS="):
            val = cmd.split("=", 1)[1].strip().strip('"')
            if val in ("GSM", "UCS2", "UTF-8"):
                self._charset = val
                return self._wrap(cmd)
            return self._wrap(cmd, terminal="+CME ERROR: 4")

        # Phonebook / Call Log storages
        if upper == "AT+CPBS=?":
            if not self.profile.supported_cpbs:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            joined = ",".join(f'"{s}"' for s in self.profile.supported_cpbs)
            return self._wrap(cmd, f"+CPBS: ({joined})")

        if upper == "AT+CPBS?":
            if not self.profile.supported_cpbs:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            entries = self._get_cpbs_entries(self._current_cpbs)
            return self._wrap(cmd, f'+CPBS: "{self._current_cpbs}",{len(entries)},50')

        if upper.startswith("AT+CPBS="):
            storage = cmd.split("=", 1)[1].strip().strip('"').upper()
            if storage not in self.profile.supported_cpbs:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            self._current_cpbs = storage
            return self._wrap(cmd)

        if upper == "AT+CPBR=?":
            if self._current_cpbs not in self.profile.supported_cpbs:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            return self._wrap(cmd, "+CPBR: (1-50),40,32")

        m_cpbr = re.match(r"^AT\+CPBR=(\d+)(?:,(\d+))?$", upper)
        if m_cpbr:
            if self._current_cpbs not in self.profile.supported_cpbs:
                return self._wrap(cmd, terminal="+CME ERROR: 4")
            start = int(m_cpbr.group(1))
            end = int(m_cpbr.group(2) or start)
            entries = self._get_cpbs_entries(self._current_cpbs)
            lines = [
                f'+CPBR: {e.index},"{e.number}",{e.num_type},"{e.name}"'
                for e in entries
                if start <= e.index <= end
            ]
            return self._wrap(cmd, *lines)

        # SMS commands
        if upper == "AT+CPMS=?":
            if not self.profile.supported_cpms:
                return self._wrap(cmd, terminal="+CMS ERROR: 302")
            joined = ",".join(f'"{s}"' for s in self.profile.supported_cpms)
            return self._wrap(cmd, f"+CPMS: ({joined}),({joined}),({joined})")

        if upper == "AT+CPMS?":
            if not self.profile.supported_cpms:
                return self._wrap(cmd, terminal="+CMS ERROR: 302")
            count = len(self.profile.sms_messages.get(self._current_cpms, []))
            return self._wrap(cmd, f'+CPMS: "{self._current_cpms}",{count},50,"{self._current_cpms}",{count},50')

        if upper.startswith("AT+CPMS="):
            storage = cmd.split("=", 1)[1].split(",")[0].strip().strip('"').upper()
            if storage not in self.profile.supported_cpms:
                return self._wrap(cmd, terminal="+CMS ERROR: 302")
            self._current_cpms = storage
            count = len(self.profile.sms_messages.get(storage, []))
            return self._wrap(cmd, f"+CPMS: {count},50,{count},50")

        if upper == "AT+CMGF=?":
            if not self.profile.supported_cpms:
                return self._wrap(cmd, terminal="+CMS ERROR: 302")
            modes = "(0,1)" if self.profile.supports_cmgf_text else "(0)"
            return self._wrap(cmd, f"+CMGF: {modes}")

        if upper == "AT+CMGF?":
            return self._wrap(cmd, f"+CMGF: {self._cmgf_mode}")

        if upper.startswith("AT+CMGF="):
            mode = cmd.split("=", 1)[1].strip()
            if mode == "1" and not self.profile.supports_cmgf_text:
                return self._wrap(cmd, terminal="+CMS ERROR: 303")
            if mode in ("0", "1"):
                self._cmgf_mode = int(mode)
                return self._wrap(cmd)
            return self._wrap(cmd, terminal="+CMS ERROR: 303")

        if upper.startswith("AT+CMGL"):
            if not self.profile.supported_cpms:
                return self._wrap(cmd, terminal="+CMS ERROR: 302")
            msgs = self.profile.sms_messages.get(self._current_cpms, [])
            lines: list[str] = []
            for msg in msgs:
                if self._cmgf_mode == 1:
                    lines.append(f'+CMGL: {msg.index},"{msg.status}","{msg.address}",,"{msg.timestamp}"')
                    lines.append(msg.body)
                else:
                    pdu = msg.pdu_hex or "07915219000000F0040B915219112233F400006211018003212104D4F29C0E"
                    lines.append(f"+CMGL: {msg.index},1,,{len(pdu) // 2}")
                    lines.append(pdu)
            return self._wrap(cmd, *lines)

        return self._wrap(cmd, terminal="ERROR")

    def _get_cpbs_entries(self, storage: str):
        if storage in ("SM", "ME"):
            return self.profile.contacts.get(storage, [])
        if storage in ("MC", "RC", "DC"):
            return self.profile.call_logs.get(storage, [])
        return []

