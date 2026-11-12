from uuid import UUID
"""Database reads and audit writes for the patient portal."""

from dataclasses import dataclass

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.allergy import Allergy
from app.models.appointment import Appointment
from app.models.audit_event import AuditEvent
from app.models.clinical_note import ClinicalNote
from app.models.medication import Medication
from app.models.message import Message
from app.models.order import Order
from app.models.outbox_event import OutboxEvent
from app.models.patient import Patient
from app.models.visit import Visit


@dataclass
class PatientPortalRecords:
    patient: Patient
    appointments: list[Appointment]
    allergies: list[Allergy]
    medications: list[Medication]
    signed_notes: list[ClinicalNote]
    signed_orders: list[Order]


class PatientPortalRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_records(self, clinic_id: UUID, patient_id: UUID) -> PatientPortalRecords | None:
        patient = self.session.query(Patient).filter_by(
            id=patient_id,
            clinic_id=clinic_id,
        ).first()
        if patient is None:
            return None
        appointments = self.session.query(Appointment).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
        ).order_by(Appointment.starts_at.desc()).limit(50).all()
        allergies = self.session.query(Allergy).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
        ).order_by(Allergy.created_at.desc()).all()
        medications = self.session.query(Medication).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
            status="active",
        ).order_by(Medication.created_at.desc()).all()
        visit_ids = [row[0] for row in self.session.query(Visit.id).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
        ).all()]
        signed_notes = []
        signed_orders = self.session.query(Order).filter(
            Order.clinic_id == clinic_id,
            Order.patient_id == patient_id,
            Order.signed_at.is_not(None),
            Order.status.notin_(("cancelled", "void")),
        ).order_by(Order.created_at.desc()).limit(100).all()
        if visit_ids:
            signed_notes = self.session.query(ClinicalNote).filter(
                ClinicalNote.clinic_id == clinic_id,
                ClinicalNote.visit_id.in_(visit_ids),
                ClinicalNote.status == "signed",
            ).order_by(ClinicalNote.created_at.desc()).limit(50).all()

        return PatientPortalRecords(
            patient=patient,
            appointments=appointments,
            allergies=allergies,
            medications=medications,
            signed_notes=signed_notes,
            signed_orders=signed_orders,
        )

    def list_appointments(self, clinic_id: UUID, patient_id: UUID) -> list[Appointment]:
        return self.session.query(Appointment).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
        ).order_by(Appointment.starts_at.desc()).limit(100).all()

    def get_appointment(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        appointment_id: UUID,
    ) -> Appointment | None:
        return self.session.query(Appointment).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
            id=appointment_id,
        ).first()

    def lock_patient(self, clinic_id: UUID, patient_id: UUID) -> Patient | None:
        return self.session.query(Patient).filter_by(
            clinic_id=clinic_id,
            id=patient_id,
        ).with_for_update().first()

    def has_appointment_conflict(
        self,
        *,
        clinic_id: UUID,
        patient_id: UUID,
        starts_at,
        ends_at,
        exclude_appointment_id: UUID | None = None,
    ) -> bool:
        query = self.session.query(Appointment.id).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.patient_id == patient_id,
            Appointment.status.notin_(("cancelled", "completed", "no_show", "void")),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        if exclude_appointment_id is not None:
            query = query.filter(Appointment.id != exclude_appointment_id)
        return query.first() is not None

    def list_messages(self, clinic_id: UUID, patient_id: UUID) -> list[Message]:
        rows = self.session.query(Message).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
            channel="portal",
        ).order_by(Message.created_at.desc()).limit(200).all()
        return list(reversed(rows))

    def list_clinic_messages(
        self,
        clinic_id: UUID,
        *,
        pending_only: bool = True,
        patient_ids: list[UUID] | None = None,
        assigned_staff_id: UUID | None = None,
    ) -> list[Message]:
        # The staff inbox must never mix staff-only coordination notes into
        # the patient conversation list. Internal notes are loaded by thread.
        query = self.session.query(Message).filter(
            Message.clinic_id == clinic_id,
            Message.channel == "portal",
        )
        if pending_only:
            query = query.filter(
                Message.direction == "inbound",
                Message.status == "needs_review",
            )
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(Message.patient_id.in_(patient_ids))
        if assigned_staff_id is not None:
            query = query.filter(Message.assigned_staff_id == assigned_staff_id)
        priority = case(
            (Message.triage_level == "emergency", 0),
            (Message.triage_level == "urgent", 1),
            else_=2,
        )
        return query.order_by(priority, Message.created_at.asc()).limit(200).all()

    def get_clinic_message(self, clinic_id: UUID, message_id: UUID) -> Message | None:
        return self.session.query(Message).filter_by(
            clinic_id=clinic_id,
            id=message_id,
        ).first()

    def list_internal_messages(self, clinic_id: UUID, parent_message_id: UUID) -> list[Message]:
        return self.session.query(Message).filter_by(
            clinic_id=clinic_id,
            channel="staff_internal",
            reply_to_message_id=parent_message_id,
        ).order_by(Message.created_at.asc()).all()

    def list_staff_conversation(self, clinic_id: UUID, staff_a: UUID, staff_b: UUID) -> list[Message]:
        return self.session.query(Message).filter(
            Message.clinic_id == clinic_id,
            Message.channel == "staff_internal",
            Message.patient_id.is_(None),
            ((Message.sender_staff_id == staff_a) & (Message.recipient_staff_id == staff_b))
            | ((Message.sender_staff_id == staff_b) & (Message.recipient_staff_id == staff_a)),
        ).order_by(Message.created_at.asc()).limit(500).all()

    def add(self, record: Appointment | Message | OutboxEvent) -> None:
        self.session.add(record)

    def add_access_audit(
        self,
        *,
        clinic_id: UUID,
        patient_id: UUID,
        actor_user_id: UUID,
        action: str = "patient.portal.read",
        resource_type: str = "patient_portal",
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.session.add(AuditEvent(
            clinic_id=clinic_id,
            actor_user_id=actor_user_id,
            patient_id=patient_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id or str(patient_id),
            details=details or {"source": "patient_portal", "purpose": "patient_self_access"},
        ))
