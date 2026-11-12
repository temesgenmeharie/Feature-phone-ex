"""Phase 3 tests: AT command registry, safety guardrails, and ATCommandEngine."""

import threading
import pytest

from app.serial.engine import ATCommandEngine
from app.serial.ports import SIMULATOR_PORT_NAME, list_available_ports
from app.serial.registry import DestructiveCommandBlockedError, SafetyClassification, validate_command_safety
from app.serial.transport import SerialTransportError


class FakeTransport:
    def __init__(self, responses: dict[str, str] | None = None, fail_read: bool = False) -> None:
        self.port_name = "COM99"
        self.baud_rate = 115200
        self._open = False
        self._responses = responses or {}
        self._last_cmd = ""
        self._fail_read = fail_read

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def write(self, data: bytes) -> int:
        self._last_cmd = data.decode("ascii").strip()
        return len(data)

    def read_until_terminal(self, terminals: tuple[str, ...], timeout_s: float) -> str:
        if self._fail_read:
            raise SerialTransportError("Simulated cable disconnect")
        return self._responses.get(self._last_cmd, "OK\r\n")


def test_registry_blocks_destructive_commands():
    assert validate_command_safety("AT+GMI") == SafetyClassification.READ_ONLY
    assert validate_command_safety("AT+CPBS=\"MC\"") == SafetyClassification.CONFIG_NON_DESTRUCTIVE

    for bad_cmd in ("AT+CMGD=1,4", "AT+CPBW=1", "AT&F", "ATD12345;", "AT+CFUN=1,1"):
        with pytest.raises(DestructiveCommandBlockedError):
            validate_command_safety(bad_cmd)


def test_port_listing_includes_simulator():
    ports = list_available_ports(include_simulator=True)
    assert any(p.port_name == SIMULATOR_PORT_NAME and p.is_simulated for p in ports)


def test_engine_command_execution_timeout_and_disconnect():
    transport = FakeTransport(
        responses={
            "AT": "AT\r\nOK\r\n",
            "AT+GMI": "Nokia\r\nOK\r\n",
            "AT+UNSUPPORTED": "+CME ERROR: 4\r\n",
            "AT+HANG": "PARTIAL_DATA_NO_TERMINAL",
        }
    )
    engine = ATCommandEngine(transport)
    engine.open()

    res_at = engine.send_command("AT")
    assert res_at.is_ok
    assert res_at.body_lines == []

    res_gmi = engine.send_command("AT+GMI")
    assert res_gmi.is_ok
    assert res_gmi.body_lines == ["Nokia"]

    res_err = engine.send_command("AT+UNSUPPORTED")
    assert res_err.terminal_status == "ERROR"

    res_timeout = engine.send_command("AT+HANG")
    assert res_timeout.terminal_status == "TIMEOUT"
    assert len(engine.logs) == 4

    # Concurrency safety check: multiple threads sending commands simultaneously
    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(5):
                r = engine.send_command("AT")
                assert r.is_ok
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors

    # Disconnection handling
    transport._fail_read = True
    with pytest.raises(SerialTransportError):
        engine.send_command("AT")
    assert engine.logs[-1].terminal_status == "DISCONNECTED"
    engine.close()

