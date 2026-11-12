"""Nurse-recorded vital observations."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.patient_vital import PatientVital


class PatientVitalRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_patient(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        *,
        visit_id: UUID | None = None,
        limit: int = 100,
    ) -> list[PatientVital]:
        query = self.session.query(PatientVital).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
        )
        if visit_id is not None:
            query = query.filter(PatientVital.visit_id == visit_id)
        return query.order_by(PatientVital.recorded_at.desc()).limit(limit).all()

    def add(self, observation: PatientVital) -> None:
        self.session.add(observation)
