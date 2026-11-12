from uuid import UUID
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClinicSignupRequest(BaseModel):
    clinic_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=150)
    phone_number: str | None = Field(default=None, max_length=30)
    clinic_phone: str | None = Field(default=None, max_length=30)
    timezone: str = Field(default="UTC", max_length=64)


class BootstrapSuperAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    full_name: str = Field(min_length=2, max_length=150)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class SessionExchangeRequest(BaseModel):
    access_token: str = Field(min_length=20)
    refresh_token: str = Field(min_length=8)
    expires_in: int | None = Field(default=3600, ge=1, le=86400)
    refresh_token_expires_in: int | None = Field(default=60 * 60 * 24 * 30, ge=1)


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordUpdateRequest(BaseModel):
    password: str = Field(min_length=8, max_length=72)


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone_number: str | None = Field(default=None, max_length=30)


class AcceptInvitationRequest(BaseModel):
    clinic_id: UUID


class AuthResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    token_type: str | None = None
    expires_in: int | None = None
    user: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    memberships: list[dict[str, Any]] | None = None
