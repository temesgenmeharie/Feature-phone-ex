"""PySerial transport implementation for physical feature phones."""

import time
import serial

from app.extraction.interfaces import SerialTransport


class SerialTransportError(RuntimeError):
    """Raised when serial I/O fails or the device disconnects."""


class PySerialTransport(SerialTransport):
    """Thread-safe low-level serial transport backed by PySerial."""

    def __init__(self, port_name: str, baud_rate: int = 115200, timeout_s: float = 3.0) -> None:
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.timeout_s = timeout_s
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port_name,
                baudrate=self.baud_rate,
                timeout=0.2,
                write_timeout=self.timeout_s,
            )
            time.sleep(0.2)
        except serial.SerialException as exc:
            raise SerialTransportError(f"Failed to open serial port {self.port_name}: {exc}") from exc

    def close(self) -> None:
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            finally:
                self._serial = None

    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def write(self, data: bytes) -> int:
        if not self.is_open() or self._serial is None:
            raise SerialTransportError("Serial port is not open")
        try:
            written = self._serial.write(data)
            self._serial.flush()
            return int(written or 0)
        except serial.SerialException as exc:
            raise SerialTransportError(f"Serial write failed on {self.port_name}: {exc}") from exc

    def read_until_terminal(self, terminals: tuple[str, ...], timeout_s: float) -> str:
        if not self.is_open() or self._serial is None:
            raise SerialTransportError("Serial port is not open")

        deadline = time.monotonic() + timeout_s
        chunks: list[str] = []

        while time.monotonic() < deadline:
            try:
                waiting = self._serial.in_waiting
                raw = self._serial.read(waiting if waiting > 0 else 1)
            except serial.SerialException as exc:
                raise SerialTransportError(f"Serial read failed (device disconnected?): {exc}") from exc

            if raw:
                text = raw.decode("utf-8", errors="replace")
                chunks.append(text)
                combined = "".join(chunks)
                lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
                if lines and any(lines[-1].startswith(t) or lines[-1] == t for t in terminals):
                    return combined
            else:
                time.sleep(0.02)

        return "".join(chunks)

