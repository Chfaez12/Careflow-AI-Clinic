"""Staff scheduling and waiting-room data access."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.staff_member import StaffMember


class AppointmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_period(
        self,
        clinic_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        *,
        status: str | None = None,
        patient_ids: list[UUID] | None = None,
    ) -> list[tuple[Appointment, Patient]]:
        query = self.session.query(Appointment, Patient).join(
            Patient, Patient.id == Appointment.patient_id
        ).filter(
            Appointment.clinic_id == clinic_id,
            Patient.clinic_id == clinic_id,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        if status:
            query = query.filter(Appointment.status == status)
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(Appointment.patient_id.in_(patient_ids))
        return query.order_by(Appointment.starts_at.asc()).all()

    def count_no_shows_for_patient(self, clinic_id: UUID, patient_id: UUID, *, before: datetime) -> int:
        return self.session.query(Appointment.id).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.patient_id == patient_id,
            Appointment.status == "no_show",
            Appointment.starts_at < before,
        ).count()

    def get(self, clinic_id: UUID, appointment_id: UUID) -> Appointment | None:
        return self.session.query(Appointment).filter_by(
            clinic_id=clinic_id,
            id=appointment_id,
        ).first()

    def get_for_update(self, clinic_id: UUID, appointment_id: UUID) -> Appointment | None:
        return self.session.query(Appointment).filter_by(
            clinic_id=clinic_id,
            id=appointment_id,
        ).with_for_update().first()

    def get_by_idempotency_key(self, clinic_id: UUID, idempotency_key: str) -> Appointment | None:
        return self.session.query(Appointment).filter_by(clinic_id=clinic_id, idempotency_key=idempotency_key).first()

    def lock_room(self, clinic_id: UUID, room_id: UUID):
        from app.models.clinic_room import ClinicRoom
        return self.session.query(ClinicRoom).filter_by(clinic_id=clinic_id, id=room_id, is_active=True).with_for_update().first()

    def patient_exists(self, clinic_id: UUID, patient_id: UUID) -> bool:
        return self.session.query(Patient.id).filter_by(clinic_id=clinic_id, id=patient_id).first() is not None

    def get_patient(self, clinic_id: UUID, patient_id: UUID) -> Patient | None:
        return self.session.query(Patient).filter_by(clinic_id=clinic_id, id=patient_id).first()

    def lock_patient(self, clinic_id: UUID, patient_id: UUID) -> Patient | None:
        return self.session.query(Patient).filter_by(
            clinic_id=clinic_id,
            id=patient_id,
        ).with_for_update().first()

    def staff_for_clinic(self, clinic_id: UUID, staff_member_id: UUID) -> StaffMember | None:
        return self.session.query(StaffMember).filter_by(
            clinic_id=clinic_id,
            id=staff_member_id,
            is_active=True,
        ).first()

    def lock_staff(self, clinic_id: UUID, staff_member_id: UUID) -> StaffMember | None:
        return self.session.query(StaffMember).filter_by(
            clinic_id=clinic_id,
            id=staff_member_id,
            is_active=True,
        ).with_for_update().first()

    def has_conflict(
        self,
        *,
        clinic_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        patient_id: UUID | None = None,
        assigned_staff_id: UUID | None = None,
        exclude_appointment_id: UUID | None = None,
    ) -> bool:
        query = self.session.query(Appointment.id).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.status.notin_(("cancelled", "completed", "no_show", "void")),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        constraints = []
        if patient_id is not None:
            constraints.append(Appointment.patient_id == patient_id)
        if assigned_staff_id is not None:
            constraints.append(Appointment.assigned_staff_id == assigned_staff_id)
        if constraints:
            query = query.filter(or_(*constraints))
        if exclude_appointment_id is not None:
            query = query.filter(Appointment.id != exclude_appointment_id)
        return query.first() is not None

    def add(self, appointment: Appointment) -> None:
        self.session.add(appointment)
