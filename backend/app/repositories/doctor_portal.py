"""Clinic-scoped reads and writes for the doctor portal."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_suggestion import AISuggestion
from app.models.allergy import Allergy
from app.models.appointment import Appointment
from app.models.clinical_note import ClinicalNote
from app.models.care_team_assignment import CareTeamAssignment
from app.models.medication import Medication
from app.models.medical_condition import MedicalCondition
from app.models.order import Order
from app.models.patient import Patient
from app.models.patient_vital import PatientVital
from app.models.visit import Visit


class DoctorPortalRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_patients(self, clinic_id: UUID, staff_id: UUID, *, search: str | None = None, limit: int = 50, offset: int = 0):
        query = self.session.query(Patient).filter(
            Patient.clinic_id == clinic_id,
            or_(
                self.session.query(CareTeamAssignment.id).filter_by(
                    clinic_id=clinic_id, staff_member_id=staff_id,
                ).filter(CareTeamAssignment.patient_id == Patient.id).exists(),
                self.session.query(Appointment.id).filter_by(
                    clinic_id=clinic_id, assigned_staff_id=staff_id,
                ).filter(Appointment.patient_id == Patient.id).exists(),
                self.session.query(Visit.id).filter_by(
                    clinic_id=clinic_id, clinician_staff_id=staff_id,
                ).filter(Visit.patient_id == Patient.id).exists(),
            ),
        )
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(or_(Patient.first_name.ilike(term), Patient.last_name.ilike(term), Patient.email.ilike(term), Patient.phone.ilike(term)))
        return query.order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset).all()

    def can_access_patient(self, clinic_id: UUID, patient_id: UUID, staff_id: UUID) -> bool:
        return self.session.query(Patient.id).filter(
            Patient.clinic_id == clinic_id,
            Patient.id == patient_id,
            or_(
                self.session.query(CareTeamAssignment.id).filter_by(
                    clinic_id=clinic_id, patient_id=patient_id, staff_member_id=staff_id,
                ).exists(),
                self.session.query(Appointment.id).filter_by(
                    clinic_id=clinic_id, patient_id=patient_id, assigned_staff_id=staff_id,
                ).exists(),
                self.session.query(Visit.id).filter_by(
                    clinic_id=clinic_id, patient_id=patient_id, clinician_staff_id=staff_id,
                ).exists(),
            ),
        ).first() is not None

    def list_appointments(self, clinic_id: UUID, staff_id: UUID, starts_at: datetime, ends_at: datetime):
        return self.session.query(Appointment, Patient).join(Patient, Patient.id == Appointment.patient_id).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.assigned_staff_id == staff_id,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
            Patient.clinic_id == clinic_id,
        ).order_by(Appointment.starts_at.asc()).all()

    def list_visits(self, clinic_id: UUID, staff_id: UUID, patient_ids: list[UUID] | None = None):
        query = self.session.query(Visit, Patient).join(Patient, Patient.id == Visit.patient_id).filter(
            Visit.clinic_id == clinic_id,
            Visit.clinician_staff_id == staff_id,
            Patient.clinic_id == clinic_id,
        )
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(Visit.patient_id.in_(patient_ids))
        return query.order_by(Visit.started_at.desc()).limit(200).all()

    def get_patient(self, clinic_id: UUID, patient_id: UUID) -> Patient | None:
        return self.session.query(Patient).filter_by(clinic_id=clinic_id, id=patient_id).first()

    def get_visit(self, clinic_id: UUID, visit_id: UUID) -> Visit | None:
        return self.session.query(Visit).filter_by(clinic_id=clinic_id, id=visit_id).first()

    def list_patient_visits(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(Visit).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(Visit.started_at.desc()).limit(100).all()

    def list_appointments_for_patient(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(Appointment).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(Appointment.starts_at.desc()).limit(100).all()

    def list_allergies(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(Allergy).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(Allergy.created_at.desc()).all()

    def get_allergy(self, clinic_id: UUID, allergy_id: UUID) -> Allergy | None:
        return self.session.query(Allergy).filter_by(clinic_id=clinic_id, id=allergy_id).first()

    def list_conditions(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(MedicalCondition).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(MedicalCondition.status, MedicalCondition.name).all()

    def get_condition(self, clinic_id: UUID, condition_id: UUID) -> MedicalCondition | None:
        return self.session.query(MedicalCondition).filter_by(clinic_id=clinic_id, id=condition_id).first()

    def list_medications(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(Medication).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(Medication.created_at.desc()).limit(200).all()

    def get_medication(self, clinic_id: UUID, medication_id: UUID) -> Medication | None:
        return self.session.query(Medication).filter_by(clinic_id=clinic_id, id=medication_id).first()

    def list_vitals(self, clinic_id: UUID, patient_id: UUID):
        return self.session.query(PatientVital).filter_by(clinic_id=clinic_id, patient_id=patient_id).order_by(PatientVital.recorded_at.desc()).limit(200).all()

    def list_notes(self, clinic_id: UUID, visit_id: UUID):
        return self.session.query(ClinicalNote).filter_by(clinic_id=clinic_id, visit_id=visit_id).order_by(ClinicalNote.version.desc()).all()

    def get_note(self, clinic_id: UUID, note_id: UUID) -> ClinicalNote | None:
        return self.session.query(ClinicalNote).filter_by(clinic_id=clinic_id, id=note_id).first()

    def list_orders(self, clinic_id: UUID, visit_id: UUID):
        return self.session.query(Order).filter_by(clinic_id=clinic_id, visit_id=visit_id).order_by(Order.created_at.desc()).all()

    def get_order(self, clinic_id: UUID, order_id: UUID) -> Order | None:
        return self.session.query(Order).filter_by(clinic_id=clinic_id, id=order_id).first()

    def list_suggestions(self, clinic_id: UUID, visit_id: UUID):
        return self.session.query(AISuggestion).filter_by(clinic_id=clinic_id, visit_id=visit_id).order_by(AISuggestion.created_at.asc()).all()

    def get_suggestion(self, clinic_id: UUID, visit_id: UUID, suggestion_id: UUID) -> AISuggestion | None:
        return self.session.query(AISuggestion).filter_by(clinic_id=clinic_id, visit_id=visit_id, id=suggestion_id).first()

    def add(self, record) -> None:
        self.session.add(record)
