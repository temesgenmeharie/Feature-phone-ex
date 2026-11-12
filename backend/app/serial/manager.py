"""Active serial session manager (physical PySerial or simulated feature phone)."""

from dataclasses import dataclass
import threading

from app.serial.engine import ATCommandEngine
from app.serial.ports import SIMULATOR_PORT_NAME
from app.serial.transport import PySerialTransport, SerialTransportError
from app.simulator.transport import SimulatedSerialTransport


@dataclass
class ConnectionStatus:
    connected: bool
    port_name: str | None = None
    baud_rate: int | None = None
    is_simulated: bool = False
    simulator_profile: str | None = None


class SerialSessionManager:
    """Thread-safe singleton holding the currently active device connection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engine: ATCommandEngine | None = None
        self._is_simulated: bool = False
        self._simulator_profile: str | None = None

    def connect(
        self,
        port_name: str,
        baud_rate: int = 115200,
        timeout_s: float = 3.0,
        use_simulator: bool = False,
        simulator_profile: str = "nokia_105_lab",
    ) -> ConnectionStatus:
        with self._lock:
            if self._engine is not None and self._engine.is_connected:
                self._engine.close()
                self._engine = None

            if use_simulator or port_name == SIMULATOR_PORT_NAME:
                transport = SimulatedSerialTransport.from_profile_id(
                    profile_id=simulator_profile, baud_rate=baud_rate
                )
                self._is_simulated = True
                self._simulator_profile = transport.profile.profile_id
            else:
                transport = PySerialTransport(port_name=port_name, baud_rate=baud_rate, timeout_s=timeout_s)
                self._is_simulated = False
                self._simulator_profile = None

            engine = ATCommandEngine(transport=transport, default_timeout_s=timeout_s)
            engine.open()
            self._engine = engine
            return self.status()

    def disconnect(self) -> ConnectionStatus:
        with self._lock:
            if self._engine is not None:
                self._engine.close()
                self._engine = None
            self._is_simulated = False
            self._simulator_profile = None
            return ConnectionStatus(connected=False)

    def status(self) -> ConnectionStatus:
        if self._engine is None or not self._engine.is_connected:
            return ConnectionStatus(connected=False)
        return ConnectionStatus(
            connected=True,
            port_name=self._engine.transport.port_name,
            baud_rate=self._engine.transport.baud_rate,
            is_simulated=self._is_simulated,
            simulator_profile=self._simulator_profile,
        )

    def require_engine(self) -> ATCommandEngine:
        if self._engine is None or not self._engine.is_connected:
            raise SerialTransportError("No device is currently connected")
        return self._engine


session_manager = SerialSessionManager()

