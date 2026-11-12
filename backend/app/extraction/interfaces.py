"""Core extraction engine interfaces for the Feature Phone Digital Forensics System."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class ExtractionCategory(str, Enum):
    DEVICE_INFO = "device_info"
    CONTACTS = "contacts"
    SMS = "sms"
    CALL_HISTORY = "call_history"
    SIM_INFO = "sim_info"


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ExtractionStatus(str, Enum):
    SUCCESS = "supported_success"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CapabilityResult:
    category: ExtractionCategory
    status: CapabilityStatus
    supported_commands: list[str] = field(default_factory=list)
    unsupported_commands: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass
class ExtractionContext:
    case_id: int
    acquisition_id: int
    acquisition_uid: str
    evidence_dir: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExtractionOutcome:
    category: ExtractionCategory
    status: ExtractionStatus
    records: list[dict[str, Any]] = field(default_factory=list)
    raw_artifacts: dict[str, str] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    error_message: str | None = None


class SerialTransport(Protocol):
    """Abstract transport for physical PySerial or simulated feature-phone connections."""

    port_name: str
    baud_rate: int

    def open(self) -> None: ...
    def close(self) -> None: ...
    def is_open(self) -> bool: ...
    def write(self, data: bytes) -> int: ...
    def read_until_terminal(self, terminals: tuple[str, ...], timeout_s: float) -> str: ...


class ExtractorPlugin(ABC):
    """Base contract for modular logical/physical extraction plugins."""

    category: ExtractionCategory

    @abstractmethod
    def probe_capabilities(self, engine: Any) -> CapabilityResult:
        """Probe whether the connected device supports this extraction category."""

    @abstractmethod
    def extract(self, engine: Any, context: ExtractionContext) -> ExtractionOutcome:
        """Execute read-only extraction and return structured records + raw responses."""

