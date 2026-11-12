# REST API Contracts (FastAPI)

Base URL: `http://127.0.0.1:8000/api/v1`

## 1. Health & System
- `GET /health` — Returns backend status, version, offline mode indicator.

## 2. Authentication & Examiners
- `POST /auth/login` — Authenticate examiner/admin, returns JWT access token and user profile.
- `GET /auth/me` — Current authenticated examiner profile.
- `POST /examiners` (Admin only) — Create examiner account.
- `GET /examiners` (Admin only) — List examiners.

## 3. Device Detection & Serial Communication
- `GET /devices/ports` — List available physical COM/serial ports plus the built-in Simulated Feature Phone port (`SIM://FEATURE_PHONE_01`).
- `POST /devices/connect` — Open serial connection (`port_name`, `baud_rate`, `timeout_s`, `use_simulator`).
- `POST /devices/disconnect` — Safely close active serial connection.
- `GET /devices/status` — Current connection state, active port, baud rate.
- `POST /devices/identify` — Run `AT`, `AT+GMI`, `AT+GMM`, `AT+GMR`, `AT+GSN`/`AT+CGSN` and probe capability matrix.
- `GET /devices/capabilities` — Return supported/unsupported AT command matrix for connected device.

## 4. Cases Management
- `POST /cases` — Create a new examination case (`case_number`, `title`, `purpose`, `device_owner_ref`, `device_description`, `notes`).
- `GET /cases` — List cases with search/status filter and dashboard summary counts.
- `GET /cases/{case_id}` — Case details + linked devices and acquisitions.
- `PATCH /cases/{case_id}` — Update case notes or status.

## 5. Acquisitions & Logical Extraction
- `POST /acquisitions` — Start an acquisition (`case_id`, `device_id`, `categories`: `["device_info", "contacts", "sms", "call_history", "sim_info"]`).
- `GET /acquisitions` — List acquisitions (filterable by `case_id`, `status`).
- `GET /acquisitions/{acquisition_id}` — Acquisition status, per-category task progress, limitations, and live AT log tail.
- `GET /acquisitions/{acquisition_id}/logs` — Full AT command/response logs for the acquisition.

## 6. Evidence Preservation & Verification
- `GET /acquisitions/{acquisition_id}/evidence` — List preserved evidence files and recorded SHA-256 hashes.
- `POST /acquisitions/{acquisition_id}/verify` — Recompute SHA-256 hashes on disk and compare against stored manifest/DB hashes; records audit event.

## 7. Data Analysis
- `GET /acquisitions/{acquisition_id}/contacts` — Search, filter by storage (`ME`/`SM`), sort, paginate.
- `GET /acquisitions/{acquisition_id}/sms` — Search, filter by status/storage/date, sort, paginate.
- `GET /acquisitions/{acquisition_id}/calls` — Search, filter by `call_type` (`missed`, `received`, `dialed`), date, sort, paginate.
- `GET /acquisitions/{acquisition_id}/sim` — SIM storage & capability summary.

## 8. Forensic Reporting & Exports
- `POST /acquisitions/{acquisition_id}/reports/pdf` — Generate forensic PDF report, hash it, and register in `evidence_files`.
- `GET /acquisitions/{acquisition_id}/export/csv` — Export structured CSV bundle (contacts, SMS, calls) and register hash.
- `GET /acquisitions/{acquisition_id}/export/json` — Export structured JSON bundle and register hash.
- `GET /evidence/{evidence_file_id}/download` — Download generated report or export file.

## 9. Audit Trail
- `GET /audit-logs` — Query audit logs (filter by `case_id`, `acquisition_id`, `action`, `examiner_id`).

