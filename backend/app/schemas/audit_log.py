from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    actor_staff_id: UUID | None
    actor_user_id: UUID | None
    patient_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    details: dict | None
    created_at: datetime
