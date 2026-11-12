from uuid import UUID
"""Database access for patient identity records."""

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.patient import Patient


class PatientRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, patient_id: UUID) -> Patient | None:
        return self.session.get(Patient, patient_id)

    def get_in_clinic(self, clinic_id: UUID, patient_id: UUID) -> Patient | None:
        return self.session.query(Patient).filter_by(
            clinic_id=clinic_id,
            id=patient_id,
        ).first()

    def list_in_clinic(
        self,
        clinic_id: UUID,
        *,
        search: str | None = None,
        patient_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Patient]:
        query = self.session.query(Patient).filter(Patient.clinic_id == clinic_id)
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(Patient.id.in_(patient_ids))
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.email.ilike(term),
                Patient.phone.ilike(term),
                Patient.external_patient_id.ilike(term),
            ))
        return query.order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset).all()

    def list_for_email(self, clinic_id: UUID, email: str) -> list[Patient]:
        return self.session.query(Patient).filter(
            Patient.clinic_id == clinic_id,
            func.lower(Patient.email) == email.strip().lower(),
        ).all()

    def add(self, patient: Patient) -> None:
        self.session.add(patient)

    def external_id_exists(
        self,
        clinic_id: UUID,
        external_patient_id: str,
        *,
        exclude_patient_id: UUID | None = None,
    ) -> bool:
        query = self.session.query(Patient.id).filter(
            Patient.clinic_id == clinic_id,
            Patient.external_patient_id == external_patient_id,
        )
        if exclude_patient_id is not None:
            query = query.filter(Patient.id != exclude_patient_id)
        return query.first() is not None

    def email_exists(self, clinic_id: UUID, email: str) -> bool:
        return self.session.query(Patient.id).filter(
            Patient.clinic_id == clinic_id,
            func.lower(Patient.email) == email.strip().lower(),
        ).first() is not None

    def add_access_audit(
        self,
        *,
        clinic_id: UUID,
        actor_user_id: UUID,
        action: str,
        patient_id: UUID | None = None,
        resource_id: str | None = None,
    ) -> None:
        self.session.add(AuditEvent(
            clinic_id=clinic_id,
            actor_user_id=actor_user_id,
            patient_id=patient_id,
            action=action,
            resource_type="patient",
            resource_id=resource_id or (str(patient_id) if patient_id else None),
            details={"source": "patient_api"},
        ))
