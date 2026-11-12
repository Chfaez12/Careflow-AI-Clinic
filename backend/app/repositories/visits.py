"""Visit lifecycle and waiting-room queries."""

from uuid import UUID

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.clinical_note import ClinicalNote
from app.models.visit import Visit
from app.models.claim import Claim


class VisitRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, clinic_id: UUID, visit_id: UUID) -> Visit | None:
        return self.session.query(Visit).filter_by(clinic_id=clinic_id, id=visit_id).first()

    def get_for_appointment(self, clinic_id: UUID, appointment_id: UUID) -> Visit | None:
        return self.session.query(Visit).filter_by(
            clinic_id=clinic_id,
            appointment_id=appointment_id,
        ).first()

    def has_signed_note(self, clinic_id: UUID, visit_id: UUID) -> bool:
        return self.session.query(ClinicalNote.id).filter_by(
            clinic_id=clinic_id,
            visit_id=visit_id,
            status="signed",
        ).first() is not None

    def list_billable(self, clinic_id: UUID, *, search: str | None = None, limit: int = 100):
        query = self.session.query(Visit, Patient).join(
            Patient, Patient.id == Visit.patient_id
        ).filter(
            Visit.clinic_id == clinic_id,
            Patient.clinic_id == clinic_id,
            exists().where(
                ClinicalNote.clinic_id == clinic_id,
                ClinicalNote.visit_id == Visit.id,
                ClinicalNote.status == "signed",
            ),
            ~exists().where(
                Claim.clinic_id == clinic_id,
                Claim.visit_id == Visit.id,
            ),
        )
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(or_(Patient.first_name.ilike(term), Patient.last_name.ilike(term)))
        return query.order_by(Visit.started_at.desc()).limit(limit).all()

    def list_for_patients(self, clinic_id: UUID, patient_ids: list[UUID]) -> list[Visit]:
        if not patient_ids:
            return []
        return self.session.query(Visit).filter(
            Visit.clinic_id == clinic_id,
            Visit.patient_id.in_(patient_ids),
            Visit.status.in_(("arrived", "in_room", "in_progress")),
        ).order_by(Visit.started_at.desc()).limit(100).all()

    def list_waiting_room(self, clinic_id: UUID) -> list[tuple[Visit, Patient]]:
        return self.session.query(Visit, Patient).join(
            Patient, Patient.id == Visit.patient_id
        ).filter(
            Visit.clinic_id == clinic_id,
            Patient.clinic_id == clinic_id,
            Visit.status.in_(("arrived", "in_room")),
        ).order_by(Visit.started_at.asc()).all()

    def add(self, visit: Visit) -> None:
        self.session.add(visit)
