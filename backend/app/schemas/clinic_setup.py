from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClinicProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=2000)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one clinic field to update")
        return self


class BusinessHourItem(BaseModel):
    weekday: int = Field(ge=0, le=6)
    is_closed: bool = False
    opens_at: time | None = None
    closes_at: time | None = None

    @model_validator(mode="after")
    def validate_hours(self):
        if any(value is not None and value.tzinfo is not None for value in (self.opens_at, self.closes_at)):
            raise ValueError("Business-hour times are clinic-local and must not include a timezone")
        if self.is_closed:
            if self.opens_at is not None or self.closes_at is not None:
                raise ValueError("Closed days must not include opening or closing times")
        elif self.opens_at is None or self.closes_at is None or self.closes_at <= self.opens_at:
            raise ValueError("Open days require a closing time later than opening time")
        return self


class BusinessHoursReplace(BaseModel):
    days: list[BusinessHourItem] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def require_each_weekday(self):
        if {item.weekday for item in self.days} != set(range(7)):
            raise ValueError("Provide exactly one business-hours entry for each weekday (0 Monday through 6 Sunday)")
        return self


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    room_type: str | None = Field(default=None, max_length=50)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    room_type: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one room field to update")
        return self


class DoctorAvailabilityCreate(BaseModel):
    staff_member_id: UUID
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if self.starts_at.tzinfo is not None or self.ends_at.tzinfo is not None:
            raise ValueError("Availability times are clinic-local and must not include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("Availability end time must be later than start time")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Availability end date must not precede its start date")
        return self


class DoctorAvailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    staff_member_id: UUID
    weekday: int
    starts_at: time
    ends_at: time
    effective_from: date
    effective_to: date | None
    is_active: bool


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    name: str
    room_type: str | None
    is_active: bool
