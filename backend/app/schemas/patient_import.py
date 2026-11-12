from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PatientImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    uploaded_by_user_id: UUID
    filename: str
    content_sha256: str
    status: str
    total_rows: int | None
    processed_rows: int
    next_row: int
    error_count: int
    created_at: datetime
    updated_at: datetime


class PatientImportErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    field: str
    message: str
    row_data: dict


class ImportPreview(BaseModel):
    job_id: UUID
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[PatientImportErrorRead]
    next_error_offset: int | None


class ImportBatchResult(BaseModel):
    job_id: UUID
    status: str
    total_rows: int
    processed_rows: int
    next_row: int
    error_count: int
    has_more: bool
