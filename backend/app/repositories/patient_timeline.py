"""Build a role-aware timeline from existing patient records."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.allergy import Allergy
from app.models.appointment import Appointment
from app.models.clinical_note import ClinicalNote
from app.models.medical_condition import MedicalCondition
from app.models.message import Message
from app.models.order import Order
from app.models.patient_vital import PatientVital
from app.models.visit import Visit


class PatientTimelineRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_items(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        *,
        include_clinical: bool,
        include_messages: bool,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> list[dict]:
        items: list[dict] = []

        def add(at, event_type, title, status, resource_id, source, summary=None):
            if at is not None and (from_at is None or at >= from_at) and (to_at is None or at < to_at):
                items.append({
                    "occurred_at": at,
                    "event_type": event_type,
                    "title": title,
                    "status": status,
                    "resource_id": resource_id,
                    "source": source,
                    "summary": summary,
                })

        appointments = self.session.query(Appointment).filter_by(
            clinic_id=clinic_id, patient_id=patient_id,
        ).all()
        for row in appointments:
            add(row.starts_at, "appointment", "Appointment", row.status, row.id, "appointments", row.reason if include_clinical else None)

        visits = self.session.query(Visit).filter_by(clinic_id=clinic_id, patient_id=patient_id).all()
        visit_ids = [row.id for row in visits]
        for row in visits:
            add(row.started_at, "visit", "Clinic visit", row.status, row.id, "visits", row.chief_complaint if include_clinical else None)

        vitals = self.session.query(PatientVital).filter_by(clinic_id=clinic_id, patient_id=patient_id).all()
        for row in vitals:
            summary = None
            if include_clinical:
                values = []
                if row.blood_pressure_systolic is not None:
                    values.append(f"BP {row.blood_pressure_systolic}/{row.blood_pressure_diastolic}")
                if row.heart_rate is not None:
                    values.append(f"HR {row.heart_rate} bpm")
                if row.temperature_c is not None:
                    values.append(f"Temp {row.temperature_c} °C")
                summary = " · ".join(values) or row.notes
            add(row.recorded_at, "vitals", "Vitals recorded", None, row.id, "patient_vitals", summary)

        if include_clinical:
            for row in self.session.query(Allergy).filter_by(clinic_id=clinic_id, patient_id=patient_id).all():
                add(row.created_at, "allergy", f"Allergy: {row.substance}", row.status, row.id, "allergies", row.reaction)
            for row in self.session.query(MedicalCondition).filter_by(clinic_id=clinic_id, patient_id=patient_id).all():
                add(row.created_at, "condition", f"Condition: {row.name}", row.status, row.id, "medical_conditions", row.notes)
            if visit_ids:
                notes = self.session.query(ClinicalNote).filter(
                    ClinicalNote.clinic_id == clinic_id,
                    ClinicalNote.visit_id.in_(visit_ids),
                ).all()
                for row in notes:
                    # Unsigned clinical drafts are private to the doctor role.
                    if row.status == "signed" or include_clinical:
                        add(
                            row.signed_at or row.created_at,
                            "clinical_note",
                            "Clinical note amendment" if row.amends_note_id else "Clinical note",
                            row.status,
                            row.id,
                            "clinical_notes",
                            row.content if row.status == "signed" else None,
                        )
                orders = self.session.query(Order).filter(
                    Order.clinic_id == clinic_id,
                    Order.patient_id == patient_id,
                ).all()
                for row in orders:
                    add(row.signed_at or row.created_at, "order", f"{row.order_type.title()} order", row.status, row.id, "orders", None)

        if include_messages:
            messages = self.session.query(Message).filter_by(
                clinic_id=clinic_id, patient_id=patient_id, channel="portal",
            ).all()
            for row in messages:
                add(row.created_at, "message", "Patient message", row.status, row.id, "messages", None)

        items.sort(key=lambda item: item["occurred_at"], reverse=True)
        return items
