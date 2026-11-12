"""Database access for resumable patient-import jobs."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.patient_import_error import PatientImportError
from app.models.patient_import_job import PatientImportJob


class PatientImportRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_job(self, job: PatientImportJob) -> None:
        self.session.add(job)

    def list_jobs(self, clinic_id: UUID, *, limit: int, offset: int):
        return self.session.query(PatientImportJob).filter_by(clinic_id=clinic_id).order_by(
            PatientImportJob.created_at.desc()
        ).offset(offset).limit(limit).all()

    def get_job(self, clinic_id: UUID, job_id: UUID) -> PatientImportJob | None:
        return self.session.query(PatientImportJob).filter_by(clinic_id=clinic_id, id=job_id).first()

    def lock_job(self, clinic_id: UUID, job_id: UUID) -> PatientImportJob | None:
        return self.session.query(PatientImportJob).filter_by(clinic_id=clinic_id, id=job_id).with_for_update().first()

    def add_error(self, error: PatientImportError) -> None:
        self.session.add(error)

    def clear_errors(self, clinic_id: UUID, job_id: UUID) -> None:
        self.session.query(PatientImportError).filter_by(clinic_id=clinic_id, job_id=job_id).delete(synchronize_session=False)

    def has_row_error(self, clinic_id: UUID, job_id: UUID, row_number: int) -> bool:
        return self.session.query(PatientImportError.id).filter_by(clinic_id=clinic_id, job_id=job_id, row_number=row_number).first() is not None

    def list_errors(self, clinic_id: UUID, job_id: UUID, *, limit: int = 100, offset: int = 0):
        return self.session.query(PatientImportError).filter_by(clinic_id=clinic_id, job_id=job_id).order_by(PatientImportError.row_number, PatientImportError.field).offset(offset).limit(limit).all()
