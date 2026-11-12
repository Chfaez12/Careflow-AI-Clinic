from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field


class ClinicRole(StrEnum):
    clinic_admin = "clinic_admin"
    doctor = "doctor"
    nurse = "nurse"
    receptionist = "receptionist"
    billing_staff = "billing_staff"
    patient = "patient"


class InvitationRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    role: ClinicRole


