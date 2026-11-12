from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VitalCreate(BaseModel):
    blood_pressure_systolic: int | None = Field(default=None, ge=40, le=300)
    blood_pressure_diastolic: int | None = Field(default=None, ge=20, le=200)
    heart_rate: int | None = Field(default=None, ge=20, le=250)
    respiratory_rate: int | None = Field(default=None, ge=5, le=80)
    temperature_c: float | None = Field(default=None, ge=25, le=45)
    oxygen_saturation: int | None = Field(default=None, ge=50, le=100)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_cm: float | None = Field(default=None, gt=0, le=250)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_readings(self):
        readings = self.model_dump(exclude={"notes"}, exclude_none=True)
        if not readings:
            raise ValueError("At least one vital measurement is required")
        if (self.blood_pressure_systolic is None) != (self.blood_pressure_diastolic is None):
            raise ValueError("Provide both blood pressure values together")
        return self


class VitalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    visit_id: UUID
    recorded_by_staff_id: UUID | None
    blood_pressure_systolic: int | None
    blood_pressure_diastolic: int | None
    heart_rate: int | None
    respiratory_rate: int | None
    temperature_c: float | None
    oxygen_saturation: int | None
    weight_kg: float | None
    height_cm: float | None
    pain_score: int | None
    notes: str | None
    recorded_at: datetime
