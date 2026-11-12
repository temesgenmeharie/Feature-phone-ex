"""Pydantic schemas for health, authentication, cases, and audit logs."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.models.forensics import CaseStatus, ExaminerRole


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    offline_mode: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class ExaminerCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    full_name: str = Field(min_length=2, max_length=128)
    email: str | None = None
    role: ExaminerRole = ExaminerRole.EXAMINER
    password: str = Field(min_length=8, max_length=128)


class ExaminerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str | None
    role: ExaminerRole
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    examiner: ExaminerOut


class CaseCreate(BaseModel):
    case_number: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=255)
    purpose: str = Field(min_length=2)
    device_owner_ref: str | None = None
    device_description: str | None = None
    notes: str | None = None


class CaseUpdate(BaseModel):
    title: str | None = None
    purpose: str | None = None
    device_owner_ref: str | None = None
    device_description: str | None = None
    notes: str | None = None
    status: CaseStatus | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_number: str
    title: str
    purpose: str
    device_owner_ref: str | None
    device_description: str | None
    notes: str | None
    status: CaseStatus
    lead_examiner_id: int
    created_at: datetime
    updated_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    examiner_id: int | None
    case_id: int | None
    acquisition_id: int | None
    action: str
    details_json: dict[str, Any] | None
    created_at: datetime

