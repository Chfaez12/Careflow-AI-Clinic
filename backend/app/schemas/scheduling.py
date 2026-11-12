from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class NoShowPredictionRead(BaseModel):
    appointment_id: UUID
    patient_id: UUID
    patient_name: str
    starts_at: datetime
    status: str
    risk_percent: int
    risk_band: str
    factors: list[str]
    model: str = "rule_based_demo"
    disclaimer: str = "Planning estimate only. Do not cancel, deny, or overbook an appointment based on this estimate."


class NoShowPredictionList(BaseModel):
    clinic_id: UUID
    day: date
    items: list[NoShowPredictionRead]
