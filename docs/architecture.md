# Feature Phone Digital Forensics Extraction System — Architecture

## 1. System Overview

This application is an offline-capable, modular desktop digital forensics platform for **logical extraction, evidence preservation, analysis, and reporting** from feature phones (keypad-based mobile devices such as Nokia, Tecno, Itel, Samsung, and compatible GSM/AT devices) over USB-to-Serial / Virtual COM Ports using Hayes AT commands.

### Core Architectural Principles

1. **Forensic Soundness & Read-Only Acquisition**
   - Never issue destructive AT commands (e.g., `AT+CMGD`, `AT+CPBW`, factory resets) during acquisition.
   - Preserve raw AT command/response transcripts verbatim before any parsing.
   - Compute and verify SHA-256 hashes for all raw and derived evidence artifacts.
   - Maintain an immutable, append-only audit log and chain-of-custody manifest per acquisition.

2. **Capability-First Probing**
   - Never assume a feature phone supports a specific AT command or storage area.
   - Query device capabilities (`AT+GMI`, `AT+GMM`, `AT+GMR`, `AT+GSN`/`AT+CGSN`, `AT+CPBS=?`, `AT+CPMS=?`, `AT+CMGF=?`) before attempting extraction.
   - Explicitly classify every category as `SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, or `FAILED`.

3. **Strict Evidence Provenance**
   - Distinguish **handset memory** (`ME`) from **SIM card storage** (`SM`).
   - Distinguish **local device call logs** (`MC`, `RC`, `DC`) from **network-generated CDRs**.
   - Never fabricate missing fields (e.g., timestamps not exposed by `AT+CPBR`); mark them `null` / `Unavailable`.

4. **Offline Desktop Deployment**
   - **Electron** shell hosts the **React 19 + TypeScript** frontend and manages the local **Python 3.12+ FastAPI** backend process on `127.0.0.1` (ephemeral or configured local port).
   - **SQLite** stores structured case, acquisition, parsed record, hash, and audit metadata locally.
   - **Filesystem Evidence Vault** stores raw AT logs, raw responses, manifests, and generated PDF/CSV/JSON reports in case-specific directories.

---

## 2. High-Level Component Architecture

```
+-----------------------------------------------------------------------+
|                        Electron Desktop Shell                         |
|  +-----------------------------------------------------------------+  |
|  |              React 19 + TypeScript + Vite Frontend              |  |
|  |  Dashboard | Devices | Cases | Acquisition | Analysis | Reports |  |
|  |  (Zustand + TanStack Query + Shadcn UI + Tailwind + Recharts)   |  |
|  +-------------------------------+---------------------------------+  |
|                                  | HTTP / WebSocket (127.0.0.1)       |
|  +-------------------------------v---------------------------------+  |
|  |                   FastAPI Backend (Python 3.12+)                |  |
|  |  +------------------+  +-------------------+  +--------------+  |  |
|  |  | Auth & RBAC      |  | Case & Audit Svc  |  | Report Gen   |  |  |
|  |  +------------------+  +-------------------+  +--------------+  |  |
|  |  +-----------------------------------------------------------+  |  |
|  |  |             Extraction Management Orchestrator            |  |  |
|  |  +----+----------------------+------------------------+------+  |  |
|  |       |                      |                        |         |  |
|  |  +----v-----+         +------v-------+         +------v------+  |  |
|  |  | Device   |         | Logical      |         | Evidence    |  |  |
|  |  | Ident. & |         | Extraction   |         | Preservation|  |  |
|  |  | Capab.   |         | Modules      |         | & SHA-256   |  |  |
|  |  +----+-----+         +------+-------+         +-------------+  |  |
|  |       |                      |                                  |  |
|  |  +----v----------------------v-------------------------------+  |  |
|  |  |          AT Command Communication Engine (Thread-Safe)    |  |  |
|  |  +----+----------------------------------------------+-------+  |  |
|  +-------|----------------------------------------------|----------+  |
|          | PySerial                                     | Virtual     |
|  +-------v--------+                             +-------v--------+    |
|  | Physical USB   |                             | Simulated      |    |
|  | Serial / COM   |                             | Feature Phone  |    |
|  +----------------+                             +----------------+    |
+-----------------------------------------------------------------------+
```

---

## 3. Modular Directory Structure

```text
FeaturePhone/
├── docs/
│   ├── architecture.md
│   ├── database_schema.md
│   ├── api_contracts.md
│   └── technical_limitations.md
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI routers (auth, devices, cases, acquisitions, analysis, reports)
│   │   ├── core/                # Config, security (JWT/hashing), logging, exceptions
│   │   ├── db/                  # SQLAlchemy engine, session, base, migrations/init
│   │   ├── models/              # SQLAlchemy ORM models (12 forensic entities)
│   │   ├── schemas/             # Pydantic v2 request/response DTOs
│   │   ├── serial/              # Port detection, PySerial transport, AT Command Engine, Command Registry
│   │   ├── simulator/           # Simulated Feature Phone (virtual serial/in-memory AT responder)
│   │   ├── extraction/          # Extraction interfaces, capability probe, Contacts/SMS/CDR/SIM extractors
│   │   ├── preservation/        # Evidence vault, raw log writer, SHA-256 hasher, manifest & verification
│   │   ├── reporting/           # PDF forensic report generator, CSV/JSON exporters
│   │   └── main.py              # FastAPI application entrypoint
│   ├── tests/                   # Pytest unit and integration test suite
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/                    # React 19 + TypeScript + Vite + Tailwind + Shadcn UI (Phase 8)
├── electron/                    # Electron main/preload packaging (Phase 10)
├── evidence/                    # Local case-specific evidence vault (gitignored contents)
├── .gitignore
└── README.md
```

---

## 4. Extraction Engine Interfaces

To support AT-command logical extraction now and future extraction plugins (e.g., vendor diagnostic protocols or authorized flash/OBEX modules) without rewriting the orchestrator, the extraction layer uses abstract contracts:

### `SerialTransport` (Abstract Transport)
- `open() -> None`
- `close() -> None`
- `is_open() -> bool`
- `write(data: bytes) -> int`
- `read_until_terminal(terminals: tuple[str, ...], timeout_s: float) -> str`

Implemented by:
- `PySerialTransport` (physical COM / `/dev/ttyUSB*` devices)
- `SimulatedSerialTransport` (in-process virtual feature phone for offline testing & training)

### `ATCommandEngine`
- Thread-safe (`threading.Lock`) per-connection command execution — prevents concurrent commands on the same port.
- Validates commands against the **Command Capability Registry** (`READ_ONLY`, `CONFIG_NON_DESTRUCTIVE`, `DESTRUCTIVE_BLOCKED`).
- Appends every `(timestamp, command, raw_response, status, duration_ms)` to the acquisition log buffer.

### `ExtractorPlugin` (Abstract Base Class for Data Categories)
- `category: ExtractionCategory` (`DEVICE_INFO`, `CONTACTS`, `SMS`, `CALL_HISTORY`, `SIM_INFO`)
- `probe_capabilities(engine: ATCommandEngine) -> CapabilityResult`
- `extract(engine: ATCommandEngine, context: ExtractionContext) -> ExtractionOutcome`
  - Returns `status` (`SUCCESS`, `PARTIAL`, `UNSUPPORTED`, `FAILED`), `records`, `raw_artifacts`, and `limitations`.

