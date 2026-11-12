# Feature Phone Digital Forensics Extraction System

An offline-capable desktop digital forensics application for **logical extraction, evidence preservation, analysis, and reporting** from feature phones (Nokia, Tecno, Itel, Samsung, and compatible AT-command devices) via USB-to-Serial / Virtual COM Ports.

> **Intended Use:** Educational laboratories, digital forensics training, and authorized forensic examinations.

## Architecture & Documentation

- [System Architecture](docs/architecture.md)
- [Database Schema](docs/database_schema.md)
- [API Contracts](docs/api_contracts.md)
- [Technical Limitations](docs/technical_limitations.md)

## Quick Start (Offline Lab)

### 1. Backend (Python 3.12+)
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Default bootstrap admin account (seeded automatically on first run):
- **Username:** `admin`
- **Password:** `ForensicsLab!2026`

### 2. Run Backend Test Suite
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

### 3. Frontend & Electron Desktop (requires Node.js 20+ LTS)
```powershell
cd frontend
npm install
npm run build

cd ..\electron
npm install
npm start
```

## Development Phases

- [x] **Phase 1:** Architecture and project setup
- [x] **Phase 2:** Database and backend foundation
- [x] **Phase 3:** Serial communication engine
- [x] **Phase 4:** Simulated feature phone
- [x] **Phase 5:** Device identification and capability detection
- [x] **Phase 6:** Logical data extraction
- [x] **Phase 7:** Evidence preservation and hashing
- [x] **Phase 8:** React frontend and dashboard
- [x] **Phase 9:** Forensic analysis and reporting
- [x] **Phase 10:** Testing, packaging, and documentation
