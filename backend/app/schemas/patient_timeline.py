from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PatientTimelineItem(BaseModel):
    occurred_at: datetime
    event_type: str
    title: str
    status: str | None = None
    resource_id: UUID
    source: str
    summary: str | None = None


class PatientTimelineRead(BaseModel):
    patient_id: UUID
    clinic_id: UUID
    items: list[PatientTimelineItem]
    limit: int
    has_more: bool
