from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReceptionAppointmentCreate(BaseModel):
    patient_id: UUID
    starts_at: datetime
    ends_at: datetime
    assigned_staff_id: UUID | None = None
    room_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must include a timezone offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError("Appointment must be scheduled in the future")
        return self


class ReceptionAppointmentReschedule(BaseModel):
    starts_at: datetime
    ends_at: datetime
    assigned_staff_id: UUID | None = None
    room_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must include a timezone offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError("Appointment must be scheduled in the future")
        return self


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ReceptionAppointmentRead(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: str
    assigned_staff_id: UUID | None
    room_id: UUID | None = None
    starts_at: datetime
    ends_at: datetime
    status: str
    reason: str | None
    source: str


class WaitingRoomItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    visit_id: UUID
    appointment_id: UUID | None
    patient_id: UUID
    patient_name: str
    status: str
    started_at: datetime
