from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PatientCreate(BaseModel):
    external_patient_id: str | None = Field(default=None, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    address: str | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    @field_validator("date_of_birth")
    @classmethod
    def birth_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value


class PatientUpdate(BaseModel):
    external_patient_id: str | None = Field(default=None, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    address: str | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    @field_validator("date_of_birth")
    @classmethod
    def birth_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    external_patient_id: str | None
    first_name: str
    last_name: str
    date_of_birth: date | None
    sex: str | None
    phone: str | None
    email: str | None
    address: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    created_at: datetime
    updated_at: datetime


class PatientList(BaseModel):
    items: list[PatientRead]
    limit: int
    offset: int
    has_more: bool
