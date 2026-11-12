from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SummarySource(BaseModel):
    source_type: str
    source_id: UUID
    recorded_at: datetime
    label: str


class SummaryFact(BaseModel):
    text: str
    source_ids: list[UUID]


class PrevisitSummaryRead(BaseModel):
    clinic_id: UUID
    appointment_id: UUID
    patient_id: UUID
    generated_at: datetime
    status: str = "draft"
    generator: str = "deterministic_demo"
    facts: list[SummaryFact]
    sources: list[SummarySource]
    disclaimer: str
