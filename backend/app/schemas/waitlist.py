from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WaitlistJoinRequest(BaseModel):
    earliest_at: datetime
    latest_at: datetime
    requested_staff_member_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.earliest_at.tzinfo is None or self.latest_at.tzinfo is None:
            raise ValueError("Waitlist dates must include a timezone offset.")
        if self.latest_at <= self.earliest_at:
            raise ValueError("latest_at must be later than earliest_at.")
        return self


class WaitlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    requested_staff_member_id: UUID | None
    earliest_at: datetime
    latest_at: datetime
    reason: str | None
    status: str
    offered_appointment_id: UUID | None
    appointment_id: UUID | None
    offered_at: datetime | None
    offer_expires_at: datetime | None
    offered_starts_at: datetime | None = None
    offered_ends_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StaffWaitlistRead(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: str
    requested_staff_member_id: UUID | None
    earliest_at: datetime
    latest_at: datetime
    reason: str | None
    status: str
    offered_starts_at: datetime | None = None
    created_at: datetime
