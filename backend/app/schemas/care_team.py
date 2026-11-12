from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CareTeamAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    staff_member_id: UUID
