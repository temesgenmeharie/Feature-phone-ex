# Database Schema Specification (SQLite + SQLAlchemy)

All extracted records are strictly linked to both an `acquisition_id` and a `case_id` to guarantee forensic traceability.

## Entities & Relationships

### 1. `examiners`
- `id` (PK, Integer)
- `username` (String, Unique, Not Null)
- `full_name` (String, Not Null)
- `email` (String, Nullable)
- `role` (Enum: `admin`, `examiner`, Not Null)
- `password_hash` (String, Not Null)
- `is_active` (Boolean, Default True)
- `created_at` (DateTime UTC)

### 2. `cases`
- `id` (PK, Integer)
- `case_number` (String, Unique, Not Null)
- `title` (String, Not Null)
- `purpose` (Text, Not Null)
- `device_owner_ref` (String, Nullable)
- `device_description` (Text, Nullable)
- `notes` (Text, Nullable)
- `status` (Enum: `open`, `in_progress`, `closed`, `archived`)
- `lead_examiner_id` (FK -> `examiners.id`, Not Null)
- `created_at` (DateTime UTC)
- `updated_at` (DateTime UTC)

### 3. `devices`
- `id` (PK, Integer)
- `case_id` (FK -> `cases.id`, Not Null)
- `port_name` (String, Nullable)
- `baud_rate` (Integer, Nullable)
- `manufacturer` (String, Nullable)
- `model` (String, Nullable)
- `firmware_revision` (String, Nullable)
- `imei` (String, Nullable)
- `is_simulated` (Boolean, Default False)
- `capabilities_json` (JSON, Nullable)
- `identified_at` (DateTime UTC, Nullable)

### 4. `acquisitions`
- `id` (PK, Integer)
- `acquisition_uid` (String, Unique, UUID, Not Null)
- `case_id` (FK -> `cases.id`, Not Null)
- `device_id` (FK -> `devices.id`, Not Null)
- `examiner_id` (FK -> `examiners.id`, Not Null)
- `extraction_method` (String, Default `"AT_LOGICAL"`)
- `status` (Enum: `pending`, `running`, `completed`, `completed_with_warnings`, `failed`, `cancelled`)
- `evidence_dir` (String, Not Null)
- `started_at` (DateTime UTC, Not Null)
- `completed_at` (DateTime UTC, Nullable)
- `limitations_json` (JSON, Nullable)
- `error_summary` (Text, Nullable)

### 5. `extraction_tasks`
- `id` (PK, Integer)
- `acquisition_id` (FK -> `acquisitions.id`, Not Null)
- `category` (Enum: `device_info`, `contacts`, `sms`, `call_history`, `sim_info`)
- `status` (Enum: `pending`, `running`, `supported_success`, `partial`, `unsupported`, `failed`, `skipped`)
- `records_extracted` (Integer, Default 0)
- `details` (Text, Nullable)
- `started_at` (DateTime UTC, Nullable)
- `completed_at` (DateTime UTC, Nullable)

### 6. `contacts`
- `id` (PK, Integer)
- `case_id` (FK -> `cases.id`, Not Null)
- `acquisition_id` (FK -> `acquisitions.id`, Not Null)
- `record_index` (Integer, Nullable)
- `name` (String, Nullable)
- `phone_number` (String, Not Null)
- `number_type` (String, Nullable)
- `storage_location` (String, Not Null) — e.g. `ME`, `SM`, `Unknown`
- `raw_entry` (Text, Nullable)

### 7. `sms_messages`
- `id` (PK, Integer)
- `case_id` (FK -> `cases.id`, Not Null)
- `acquisition_id` (FK -> `acquisitions.id`, Not Null)
- `message_index` (Integer, Nullable)
- `status` (String, Nullable) — e.g. `REC UNREAD`, `REC READ`, `STO UNSENT`, `STO SENT`
- `sender_or_recipient` (String, Nullable)
- `timestamp_raw` (String, Nullable)
- `timestamp_iso` (DateTime, Nullable)
- `content` (Text, Nullable)
- `storage_location` (String, Not Null) — e.g. `ME`, `SM`
- `pdu_hex` (Text, Nullable)
- `raw_entry` (Text, Nullable)

### 8. `call_records`
- `id` (PK, Integer)
- `case_id` (FK -> `cases.id`, Not Null)
- `acquisition_id` (FK -> `acquisitions.id`, Not Null)
- `call_type` (Enum: `missed`, `received`, `dialed`, `unknown`, Not Null)
- `record_index` (Integer, Nullable)
- `phone_number` (String, Not Null)
- `contact_name` (String, Nullable)
- `timestamp_raw` (String, Nullable)
- `timestamp_iso` (DateTime, Nullable)
- `duration_seconds` (Integer, Nullable)
- `storage_location` (String, Not Null) — e.g. `MC`, `RC`, `DC`
- `is_cdr_level` (Boolean, Default False) — explicitly distinguishes limited phonebook call logs from full CDRs
- `raw_entry` (Text, Nullable)

### 9. `evidence_files`
- `id` (PK, Integer)
- `case_id` (FK -> `cases.id`, Not Null)
- `acquisition_id` (FK -> `acquisitions.id`, Not Null)
- `file_name` (String, Not Null)
- `file_path` (String, Not Null)
- `file_type` (Enum: `raw_at_log`, `raw_response`, `manifest`, `export_csv`, `export_json`, `report_pdf`)
- `file_size_bytes` (Integer, Not Null)
- `is_immutable` (Boolean, Default True)
- `created_at` (DateTime UTC)

### 10. `evidence_hashes`
- `id` (PK, Integer)
- `evidence_file_id` (FK -> `evidence_files.id`, Unique, Not Null)
- `algorithm` (String, Default `"SHA-256"`, Not Null)
- `digest_hex` (String(64), Not Null)
- `computed_at` (DateTime UTC, Not Null)
- `last_verified_at` (DateTime UTC, Nullable)
- `last_verification_passed` (Boolean, Nullable)

### 11. `at_command_logs`
- `id` (PK, Integer)
- `acquisition_id` (FK -> `acquisitions.id`, Nullable)
- `device_id` (FK -> `devices.id`, Nullable)
- `command` (String, Not Null)
- `response` (Text, Not Null)
- `terminal_status` (String, Not Null) — `OK`, `ERROR`, `TIMEOUT`, `DISCONNECTED`
- `duration_ms` (Integer, Not Null)
- `executed_at` (DateTime UTC, Not Null)

### 12. `audit_logs`
- `id` (PK, Integer)
- `examiner_id` (FK -> `examiners.id`, Nullable)
- `case_id` (FK -> `cases.id`, Nullable)
- `acquisition_id` (FK -> `acquisitions.id`, Nullable)
- `action` (String, Not Null) — e.g. `LOGIN`, `CASE_CREATED`, `PORT_CONNECTED`, `ACQUISITION_STARTED`, `HASH_VERIFIED`, `REPORT_GENERATED`
- `details_json` (JSON, Nullable)
- `created_at` (DateTime UTC, Not Null)

