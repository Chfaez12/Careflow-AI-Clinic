from decimal import Decimal
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Code = Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9.-]+$")]


class ClaimCreate(BaseModel):
    patient_id: UUID
    visit_id: UUID
    payer_name: str | None = Field(default=None, max_length=200)
    diagnosis_codes: list[Code] = Field(default_factory=list, max_length=20)
    procedure_codes: list[Code] = Field(default_factory=list, max_length=30)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ClaimUpdate(BaseModel):
    payer_name: str | None = Field(default=None, max_length=200)
    rejection_reason: str | None = Field(default=None, max_length=5000)
    diagnosis_codes: list[Code] = Field(default_factory=list, max_length=20)
    procedure_codes: list[Code] = Field(default_factory=list, max_length=30)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    visit_id: UUID | None
    payer_name: str | None
    payer_claim_id: str | None
    status: str
    diagnosis_codes: list
    procedure_codes: list
    amount: Decimal | None
    rejection_reason: str | None
    submitted_at: datetime | None
    created_at: datetime


class ClaimListItem(ClaimRead):
    patient_name: str


class ClaimList(BaseModel):
    items: list[ClaimListItem]
    limit: int
    offset: int
    has_more: bool
