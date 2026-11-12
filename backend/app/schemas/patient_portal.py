from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppointmentBookingRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    assigned_staff_id: UUID
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
            raise ValueError("Appointment must be booked in the future")
        return self


class AppointmentRescheduleRequest(AppointmentBookingRequest):
    pass


class AppointmentCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class PortalMessageCreate(BaseModel):
    target_staff_member_id: UUID
    target_role: str = Field(pattern="^(doctor|receptionist)$")
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def reject_blank_message(self):
        if not self.body.strip():
            raise ValueError("Message body cannot be blank")
        return self


class StaffMessageReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def reject_blank_message(self):
        if not self.body.strip():
            raise ValueError("Reply body cannot be blank")
        return self


class InternalMessageCreate(BaseModel):
    recipient_staff_member_id: UUID
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def reject_blank_message(self):
        if not self.body.strip():
            raise ValueError("Internal message body cannot be blank")
        return self


class PortalAppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    starts_at: datetime
    ends_at: datetime
    assigned_staff_id: UUID | None
    room_id: UUID | None
    status: str
    reason: str | None
    cancellation_reason: str | None


class PortalMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID | None
    direction: str
    channel: str
    body: str
    status: str
    triage_level: str | None
    assigned_staff_id: UUID | None
    sender_staff_id: UUID | None
    reply_to_message_id: UUID | None
    created_at: datetime
    confirmation: str | None = None
    safety_notice: str | None = None


class PortalDoctorRead(BaseModel):
    staff_member_id: UUID
    full_name: str


class PortalMessageRecipientRead(BaseModel):
    staff_member_id: UUID
    full_name: str
    role: str


class InternalMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_staff_id: UUID | None
    assigned_staff_id: UUID | None
    recipient_staff_id: UUID | None = None
    body: str
    created_at: datetime


class StaffMessageThread(BaseModel):
    patient_message: PortalMessageRead
    internal_messages: list[InternalMessageRead]
