"""Clinic-admin CSV validation, preview and resumable patient import APIs."""

import csv
import hashlib
import io
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.dependencies.auth import AuthContext, require_clinic_role
from app.models.patient import Patient
from app.models.patient_import_error import PatientImportError
from app.models.patient_import_job import PatientImportJob
from app.repositories.audit_events import AuditEventRepository
from app.repositories.patient_imports import PatientImportRepository
from app.repositories.patients import PatientRepository
from app.schemas.patient import PatientCreate
from app.schemas.patient_import import ImportBatchResult, ImportPreview, PatientImportErrorRead, PatientImportJobRead
from app.services.storage_service import FlociS3StorageService


router = APIRouter(prefix="/auth/clinics/{clinic_id}/imports/patients", tags=["Patient Import"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_DATA_ROWS = 20_000
REQUIRED_HEADERS = {"first_name", "last_name"}
ALLOWED_HEADERS = set(PatientCreate.model_fields)


def _audit(context: AuthContext, clinic_id: UUID, action: str, job_id: UUID, details: dict | None = None):
    AuditEventRepository(context.db).record(
        clinic_id=clinic_id,
        actor_user_id=context.user.id,
        action=action,
        resource_type="patient_import_job",
        resource_id=str(job_id),
        details={"source": "patient_import_api", **(details or {})},
    )


def _decode_csv(content: bytes) -> tuple[list[str], list[tuple[int, dict[str, str | None]]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV file must use UTF-8 encoding.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = [str(item or "").strip() for item in (reader.fieldnames or [])]
        if not headers or any(not header for header in headers) or len(headers) != len(set(headers)):
            raise HTTPException(status_code=422, detail="CSV must have unique, non-empty column names in its first row.")
        rows = []
        for row_number, raw in enumerate(reader, start=2):
            if row_number > MAX_DATA_ROWS + 1:
                raise HTTPException(status_code=413, detail=f"CSV cannot contain more than {MAX_DATA_ROWS} data rows.")
            if None in raw:
                raise HTTPException(status_code=422, detail=f"CSV row {row_number} has more values than the header row.")
            cleaned = {key: (value.strip() or None) if value is not None else None for key, value in raw.items()}
            rows.append((row_number, cleaned))
        return headers, rows
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"CSV could not be parsed: {exc}") from exc


def _validate_headers(headers: list[str]) -> list[tuple[str, str]]:
    problems = []
    missing = REQUIRED_HEADERS - set(headers)
    unknown = set(headers) - ALLOWED_HEADERS
    for field in sorted(missing):
        problems.append((field, "Required column is missing."))
    for field in sorted(unknown):
        problems.append((field, "Column is not supported by the patient import format."))
    return problems


def _row_values(row: dict[str, str | None]) -> PatientCreate:
    return PatientCreate.model_validate(row)


@router.post("", response_model=PatientImportJobRead, status_code=status.HTTP_201_CREATED)
async def upload_patient_import(
    clinic_id: UUID,
    file: UploadFile = File(...),
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    filename = Path(file.filename or "patients.csv").name[:255]
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded CSV is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 20 MB upload limit.")
    job_id = uuid4()
    storage_key = f"{clinic_id}/{job_id}/source.csv"
    storage = FlociS3StorageService()
    await storage.upload_import(storage_key, content)
    job = PatientImportJob(
        id=job_id,
        clinic_id=clinic_id,
        uploaded_by_user_id=context.user.id,
        filename=filename,
        storage_key=storage_key,
        content_sha256=hashlib.sha256(content).hexdigest(),
        status="uploaded",
    )
    repository = PatientImportRepository(context.db)
    repository.add_job(job)
    try:
        context.db.flush()
        _audit(context, clinic_id, "patient_import.uploaded", job.id, {"filename": filename, "bytes": len(content)})
        context.db.commit()
    except SQLAlchemyError as exc:
        context.db.rollback()
        await storage.delete_import(storage_key)
        raise HTTPException(status_code=500, detail="Could not create the patient import job.") from exc
    context.db.refresh(job)
    return job


@router.get("", response_model=list[PatientImportJobRead])
async def list_patient_imports(
    clinic_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    return PatientImportRepository(context.db).list_jobs(clinic_id, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=PatientImportJobRead)
async def get_patient_import(clinic_id: UUID, job_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    job = PatientImportRepository(context.db).get_job(clinic_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Patient import job not found in this clinic.")
    return job


@router.post("/{job_id}/preview", response_model=ImportPreview)
async def preview_patient_import(clinic_id: UUID, job_id: UUID, context: AuthContext = Depends(require_clinic_role("clinic_admin"))):
    imports = PatientImportRepository(context.db)
    job = imports.lock_job(clinic_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Patient import job not found in this clinic.")
    if job.status in {"importing", "completed"}:
        raise HTTPException(status_code=409, detail="A started or completed import cannot be previewed again.")
    content = await FlociS3StorageService().download_import(job.storage_key)
    if hashlib.sha256(content).hexdigest() != job.content_sha256:
        raise HTTPException(status_code=409, detail="Stored CSV checksum does not match the uploaded file.")
    headers, rows = _decode_csv(content)
    imports.clear_errors(clinic_id, job.id)
    header_errors = _validate_headers(headers)
    invalid_rows: set[int] = set()
    if header_errors:
        for field, message in header_errors:
            imports.add_error(PatientImportError(clinic_id=clinic_id, job_id=job.id, row_number=1, field=field, message=message, row_data={"headers": headers}))
            invalid_rows.add(1)
    patient_repository = PatientRepository(context.db)
    seen_external_ids: set[str] = set()
    valid_count = 0
    if not header_errors:
        for row_number, raw in rows:
            try:
                patient = _row_values(raw)
                external_id = patient.external_patient_id
                if external_id and (external_id in seen_external_ids or patient_repository.external_id_exists(clinic_id, external_id)):
                    raise ValueError("external_patient_id is already used in this clinic or this file")
                if external_id:
                    seen_external_ids.add(external_id)
                valid_count += 1
            except (ValidationError, ValueError) as exc:
                if isinstance(exc, ValidationError):
                    errors = exc.errors()
                    issues = [(str(issue["loc"][0]) if issue.get("loc") else "row", issue.get("msg", "Invalid value.")) for issue in errors]
                else:
                    message = str(exc)
                    field = "external_patient_id" if "external_patient_id" in message else "email" if "email" in message else "row"
                    issues = [(field, message)]
                invalid_rows.add(row_number)
                for field, message in issues:
                    imports.add_error(PatientImportError(
                        clinic_id=clinic_id, job_id=job.id, row_number=row_number, field=field,
                        message=message[:1000], row_data=raw,
                    ))
    job.total_rows = len(rows)
    job.processed_rows = 0
    job.next_row = 2
    context.db.flush()
    job.error_count = context.db.query(PatientImportError.id).filter_by(clinic_id=clinic_id, job_id=job.id).count()
    job.status = "invalid" if header_errors else "previewed"
    _audit(context, clinic_id, "patient_import.previewed", job.id,
           {"total_rows": len(rows), "valid_rows": valid_count, "invalid_rows": len(invalid_rows)})
    context.db.commit()
    errors = imports.list_errors(clinic_id, job.id, limit=100)
    return ImportPreview(job_id=job.id, status=job.status, total_rows=len(rows), valid_rows=valid_count,
                         invalid_rows=len(invalid_rows), errors=errors,
                         next_error_offset=100 if job.error_count > 100 else None)


@router.get("/{job_id}/errors", response_model=list[PatientImportErrorRead])
async def list_patient_import_errors(
    clinic_id: UUID,
    job_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    imports = PatientImportRepository(context.db)
    if imports.get_job(clinic_id, job_id) is None:
        raise HTTPException(status_code=404, detail="Patient import job not found in this clinic.")
    return imports.list_errors(clinic_id, job_id, limit=limit, offset=offset)


@router.post("/{job_id}/run", response_model=ImportBatchResult)
async def run_patient_import_batch(
    clinic_id: UUID,
    job_id: UUID,
    batch_size: int = Query(default=250, ge=1, le=1000),
    context: AuthContext = Depends(require_clinic_role("clinic_admin")),
):
    imports = PatientImportRepository(context.db)
    job = imports.lock_job(clinic_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Patient import job not found in this clinic.")
    if job.status not in {"previewed", "importing"} or job.total_rows is None:
        raise HTTPException(status_code=409, detail="Preview the CSV successfully before starting its import.")
    content = await FlociS3StorageService().download_import(job.storage_key)
    if hashlib.sha256(content).hexdigest() != job.content_sha256:
        raise HTTPException(status_code=409, detail="Stored CSV checksum does not match the uploaded file.")
    headers, rows = _decode_csv(content)
    if _validate_headers(headers):
        raise HTTPException(status_code=409, detail="CSV headers are invalid; upload a corrected file.")
    selected = [(number, row) for number, row in rows if number >= job.next_row][:batch_size]
    patient_repository = PatientRepository(context.db)
    seen_external_ids: set[str] = set()
    for row_number, raw in selected:
        is_already_invalid = imports.has_row_error(clinic_id, job.id, row_number)
        try:
            patient_data = _row_values(raw)
            external_id = patient_data.external_patient_id
            duplicate_field = None
            duplicate_message = None
            if external_id and (external_id in seen_external_ids or patient_repository.external_id_exists(clinic_id, external_id)):
                duplicate_field, duplicate_message = "external_patient_id", "external_patient_id is already used in this clinic"
            if duplicate_field:
                if not is_already_invalid:
                    imports.add_error(PatientImportError(clinic_id=clinic_id, job_id=job.id, row_number=row_number,
                        field=duplicate_field, message=duplicate_message, row_data=raw))
                continue
            if not is_already_invalid:
                patient = Patient(clinic_id=clinic_id, **patient_data.model_dump())
                patient_repository.add(patient)
                context.db.flush()
                if external_id:
                    seen_external_ids.add(external_id)
        except (ValidationError, ValueError) as exc:
            if not is_already_invalid:
                errors = exc.errors() if isinstance(exc, ValidationError) else None
                issue = errors[0] if errors else {"loc": ("row",), "msg": str(exc)}
                imports.add_error(PatientImportError(clinic_id=clinic_id, job_id=job.id, row_number=row_number,
                    field=str(issue["loc"][0]) if issue.get("loc") else "row",
                    message=issue.get("msg", "Invalid value.")[:1000], row_data=raw))
    if selected:
        job.next_row = selected[-1][0] + 1
        job.processed_rows += len(selected)
    complete = job.processed_rows >= job.total_rows
    job.status = "completed" if complete else "importing"
    context.db.flush()
    job.error_count = context.db.query(PatientImportError.id).filter_by(clinic_id=clinic_id, job_id=job.id).count()
    _audit(context, clinic_id, "patient_import.batch_processed", job.id,
           {"batch_rows": len(selected), "processed_rows": job.processed_rows, "complete": complete})
    context.db.commit()
    return ImportBatchResult(job_id=job.id, status=job.status, total_rows=job.total_rows,
                             processed_rows=job.processed_rows, next_row=job.next_row,
                             error_count=job.error_count, has_more=not complete)
