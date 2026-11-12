from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisitConsentRequest(BaseModel):
    consent_given: bool


class VisitUpdate(BaseModel):
    chief_complaint: str | None = Field(default=None, max_length=5000)


class AllergyCreate(BaseModel):
    substance: str = Field(min_length=1, max_length=200)
    reaction: str | None = Field(default=None, max_length=5000)
    severity: str | None = Field(default=None, max_length=30)


class AllergyUpdate(BaseModel):
    reaction: str | None = Field(default=None, max_length=5000)
    severity: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, pattern="^(active|inactive|resolved)$")

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one allergy field to update")
        return self


class ConditionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    code_system: str | None = Field(default=None, max_length=50)
    onset_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ConditionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|resolved|inactive)$")
    resolved_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one condition field to update")
        return self


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50000)

    @model_validator(mode="after")
    def reject_blank(self):
        if not self.content.strip():
            raise ValueError("Note content cannot be blank")
        return self


class NoteUpdate(NoteCreate):
    pass


class NoteAmendmentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reject_blank_amendment(self):
        if not self.content.strip() or not self.reason.strip():
            raise ValueError("Amendment content and reason cannot be blank")
        return self


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    visit_id: UUID
    amends_note_id: UUID | None
    amendment_reason: str | None
    author_staff_id: UUID | None
    version: int
    content: str
    status: str
    signed_by_staff_id: UUID | None
    signed_at: datetime | None
    created_at: datetime


class PrescriptionCreate(BaseModel):
    medication_name: str = Field(min_length=1, max_length=200)
    rxnorm_code: str | None = Field(default=None, max_length=50)
    dose: str = Field(min_length=1, max_length=100)
    route: str = Field(min_length=1, max_length=50)
    frequency: str = Field(min_length=1, max_length=100)
    instructions: str | None = Field(default=None, max_length=5000)
    duration_days: int | None = Field(default=None, ge=1, le=3650)


class OrderSignRequest(BaseModel):
    override_reason: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def reject_blank_override(self):
        if self.override_reason is not None and not self.override_reason.strip():
            raise ValueError("override_reason cannot be blank")
        return self


class LabOrderCreate(BaseModel):
    test_name: str = Field(min_length=1, max_length=200)
    priority: str = Field(default="routine", pattern="^(routine|urgent|stat)$")
    indication: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=5000)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    visit_id: UUID | None
    created_by_staff_id: UUID | None
    order_type: str
    status: str
    details: dict
    notes: str | None
    signed_by_staff_id: UUID | None
    signed_at: datetime | None
    created_at: datetime


class OrderDraftUpdate(BaseModel):
    details: dict
    notes: str | None = Field(default=None, max_length=5000)


class SuggestionDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    decision_notes: str | None = Field(default=None, max_length=5000)


class DraftNoteRequest(BaseModel):
    subjective: str | None = Field(default=None, max_length=12000)
    objective: str | None = Field(default=None, max_length=12000)
    assessment: str | None = Field(default=None, max_length=12000)
    plan: str | None = Field(default=None, max_length=12000)

    @model_validator(mode="after")
    def require_note_content(self):
        if not any(value and value.strip() for value in (self.subjective, self.objective, self.assessment, self.plan)):
            raise ValueError("Provide at least one clinician-entered note section.")
        return self


class AISuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID | None
    visit_id: UUID | None
    suggestion_type: str
    content: str
    structured_data: dict | None
    model_name: str | None
    model_version: str | None
    status: str
    decision_notes: str | None
    created_at: datetime


class PatientListItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    phone: str | None = None
    email: str | None = None
