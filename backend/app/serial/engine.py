"""Reusable, thread-safe AT Command Communication Engine."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
import time

from app.extraction.interfaces import SerialTransport
from app.serial.registry import validate_command_safety
from app.serial.transport import SerialTransportError

logger = logging.getLogger(__name__)

TERMINAL_TOKENS: tuple[str, ...] = ("OK", "ERROR", "+CME ERROR", "+CMS ERROR")


@dataclass(frozen=True)
class ATCommandResult:
    command: str
    raw_response: str
    terminal_status: str  # OK | ERROR | TIMEOUT | DISCONNECTED
    duration_ms: int
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_ok(self) -> bool:
        return self.terminal_status == "OK"

    @property
    def body_lines(self) -> list[str]:
        """Return non-empty response lines excluding echoed command and terminal OK/ERROR."""
        lines: list[str] = []
        cmd_upper = self.command.strip().upper()
        for raw_line in self.raw_response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper() == cmd_upper:
                continue
            if any(line == t or line.startswith(f"{t}:") for t in TERMINAL_TOKENS):
                continue
            lines.append(line)
        return lines


class ATCommandEngine:
    """Serializes AT command execution, enforces read-only safety, and logs all traffic."""

    def __init__(self, transport: SerialTransport, default_timeout_s: float = 3.0) -> None:
        self.transport = transport
        self.default_timeout_s = default_timeout_s
        self._lock = threading.Lock()
        self.logs: list[ATCommandResult] = []

    def open(self) -> None:
        with self._lock:
            if not self.transport.is_open():
                self.transport.open()

    def close(self) -> None:
        with self._lock:
            if self.transport.is_open():
                self.transport.close()

    @property
    def is_connected(self) -> bool:
        return self.transport.is_open()

    def send_command(self, command: str, timeout_s: float | None = None) -> ATCommandResult:
        """Validate safety, send AT command under lock, read until terminal, and log."""
        clean_cmd = command.strip()
        validate_command_safety(clean_cmd)
        effective_timeout = timeout_s if timeout_s is not None else self.default_timeout_s

        with self._lock:
            if not self.transport.is_open():
                raise SerialTransportError("Cannot send AT command: transport is not open")

            t0 = time.monotonic()
            try:
                self.transport.write((clean_cmd + "\r\n").encode("ascii", errors="ignore"))
                raw_response = self.transport.read_until_terminal(TERMINAL_TOKENS, effective_timeout)
                terminal_status = self._classify_terminal(raw_response)
            except SerialTransportError as exc:
                duration_ms = int((time.monotonic() - t0) * 1000)
                result = ATCommandResult(
                    command=clean_cmd,
                    raw_response=str(exc),
                    terminal_status="DISCONNECTED",
                    duration_ms=duration_ms,
                )
                self.logs.append(result)
                logger.warning("AT command %s failed due to disconnection: %s", clean_cmd, exc)
                raise

            duration_ms = int((time.monotonic() - t0) * 1000)
            result = ATCommandResult(
                command=clean_cmd,
                raw_response=raw_response,
                terminal_status=terminal_status,
                duration_ms=duration_ms,
            )
            self.logs.append(result)
            logger.debug("AT %s -> %s (%d ms)", clean_cmd, terminal_status, duration_ms)
            return result

    @staticmethod
    def _classify_terminal(raw_response: str) -> str:
        lines = [ln.strip() for ln in raw_response.splitlines() if ln.strip()]
        if not lines:
            return "TIMEOUT"
        last = lines[-1]
        if last == "OK":
            return "OK"
        if last == "ERROR" or last.startswith("+CME ERROR") or last.startswith("+CMS ERROR"):
            return "ERROR"
        return "TIMEOUT"

