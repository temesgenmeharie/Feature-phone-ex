"""Phase 2 tests: health, auth, RBAC, cases, audit logs, and ORM relationships."""

from app.models.forensics import CaseStatus


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["offline_mode"] is True


def test_login_and_rbac(client):
    bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    admin_token = _login(client, "admin", "AdminPass123!")
    examiner_token = _login(client, "examiner1", "ExaminerPass123!")

    # Examiner cannot create new examiners
    forbidden = client.post(
        "/api/v1/examiners",
        headers={"Authorization": f"Bearer {examiner_token}"},
        json={
            "username": "examiner2",
            "full_name": "Second Examiner",
            "role": "examiner",
            "password": "Password123!",
        },
    )
    assert forbidden.status_code == 403

    # Admin can create examiner
    created = client.post(
        "/api/v1/examiners",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "examiner2",
            "full_name": "Second Examiner",
            "role": "examiner",
            "password": "Password123!",
        },
    )
    assert created.status_code == 201
    assert created.json()["username"] == "examiner2"


def test_case_lifecycle_and_audit_trail(client):
    token = _login(client, "examiner1", "ExaminerPass123!")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "case_number": "CASE-2026-001",
            "title": "Nokia 105 Lab Examination",
            "purpose": "Forensic training logical extraction",
            "device_owner_ref": "LAB-DEVICE-01",
            "device_description": "Nokia 105 TA-1174",
            "notes": "Initial intake",
        },
    )
    assert create_resp.status_code == 201
    case_data = create_resp.json()
    case_id = case_data["id"]
    assert case_data["case_number"] == "CASE-2026-001"
    assert case_data["status"] == CaseStatus.OPEN.value

    list_resp = client.get("/api/v1/cases?search=Nokia", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    patch_resp = client.patch(
        f"/api/v1/cases/{case_id}",
        headers=headers,
        json={"status": "in_progress", "notes": "Connected to lab workstation"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_progress"

    audit_resp = client.get(f"/api/v1/audit-logs?case_id={case_id}", headers=headers)
    assert audit_resp.status_code == 200
    actions = [entry["action"] for entry in audit_resp.json()]
    assert "CASE_CREATED" in actions
    assert "CASE_UPDATED" in actions

