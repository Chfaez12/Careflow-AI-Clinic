"""Tenant-scoped waitlist persistence and transactional slot offers."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.outbox_event import OutboxEvent
from app.models.patient import Patient
from app.models.waitlist_entry import WaitlistEntry


class WaitlistRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, entry: WaitlistEntry) -> None:
        self.session.add(entry)

    def list_for_patient(self, clinic_id: UUID, patient_id: UUID) -> list[WaitlistEntry]:
        return self.session.query(WaitlistEntry).filter_by(
            clinic_id=clinic_id, patient_id=patient_id,
        ).order_by(WaitlistEntry.created_at.desc()).limit(100).all()

    def list_for_clinic(self, clinic_id: UUID, *, include_closed: bool = False) -> list[tuple[WaitlistEntry, Patient, Appointment | None]]:
        query = self.session.query(WaitlistEntry, Patient).join(
            Patient, Patient.id == WaitlistEntry.patient_id,
        ).filter(
            WaitlistEntry.clinic_id == clinic_id,
            Patient.clinic_id == clinic_id,
        )
        if not include_closed:
            query = query.filter(WaitlistEntry.status.in_(("waiting", "offered")))
        rows = query.order_by(WaitlistEntry.created_at.asc()).limit(500).all()
        return [
            (entry, patient, self.session.query(Appointment).filter_by(
                clinic_id=clinic_id, id=entry.offered_appointment_id,
            ).first() if entry.offered_appointment_id else None)
            for entry, patient in rows
        ]

    def get_for_patient(self, clinic_id: UUID, patient_id: UUID, entry_id: UUID, *, for_update: bool = False) -> WaitlistEntry | None:
        query = self.session.query(WaitlistEntry).filter_by(
            clinic_id=clinic_id, patient_id=patient_id, id=entry_id,
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    def has_open_entry(self, clinic_id: UUID, patient_id: UUID) -> bool:
        return self.session.query(WaitlistEntry.id).filter(
            WaitlistEntry.clinic_id == clinic_id,
            WaitlistEntry.patient_id == patient_id,
            WaitlistEntry.status.in_(("waiting", "offered")),
        ).first() is not None

    def offer_next_for_slot(self, clinic_id: UUID, appointment: Appointment) -> WaitlistEntry | None:
        now = datetime.now(timezone.utc)
        if appointment.starts_at <= now:
            return None
        query = self.session.query(WaitlistEntry).filter(
            WaitlistEntry.clinic_id == clinic_id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.earliest_at <= appointment.starts_at,
            WaitlistEntry.latest_at >= appointment.ends_at,
            (WaitlistEntry.requested_staff_member_id.is_(None)
             | (WaitlistEntry.requested_staff_member_id == appointment.assigned_staff_id)),
        ).order_by(WaitlistEntry.created_at.asc()).with_for_update(skip_locked=True)
        entry = query.first()
        if entry is None:
            return None
        entry.status = "offered"
        entry.offered_appointment_id = appointment.id
        entry.offered_at = now
        entry.offer_expires_at = min(now + timedelta(minutes=30), appointment.starts_at)
        self.session.add(OutboxEvent(
            clinic_id=clinic_id,
            event_type="waitlist.slot_offer.created",
            aggregate_type="waitlist_entry",
            aggregate_id=str(entry.id),
            payload={
                "waitlist_entry_id": str(entry.id),
                "patient_id": str(entry.patient_id),
                "appointment_id": str(appointment.id),
                "starts_at": appointment.starts_at.isoformat(),
                "ends_at": appointment.ends_at.isoformat(),
                "assigned_staff_id": str(appointment.assigned_staff_id) if appointment.assigned_staff_id else None,
                "room_id": str(appointment.room_id) if appointment.room_id else None,
                "expires_at": entry.offer_expires_at.isoformat(),
            },
        ))
        return entry
