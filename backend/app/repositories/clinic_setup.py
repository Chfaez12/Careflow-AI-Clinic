"""Clinic onboarding and scheduling configuration queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.clinic_business_hour import ClinicBusinessHour
from app.models.clinic_room import ClinicRoom
from app.models.doctor_availability import DoctorAvailability
from app.models.patient import Patient
from app.models.staff_member import StaffMember
from app.models.clinic_membership import ClinicMembership
from app.models.user import UserProfile
from app.models.patient_import_job import PatientImportJob


class ClinicSetupRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_business_hours(self, clinic_id: UUID):
        return self.session.query(ClinicBusinessHour).filter_by(clinic_id=clinic_id).order_by(ClinicBusinessHour.weekday).all()

    def get_business_hour(self, clinic_id: UUID, weekday: int):
        return self.session.query(ClinicBusinessHour).filter_by(clinic_id=clinic_id, weekday=weekday).first()

    def replace_business_hours(self, clinic_id: UUID, values: list[dict]) -> None:
        self.session.query(ClinicBusinessHour).filter_by(clinic_id=clinic_id).delete(synchronize_session=False)
        self.session.add_all(ClinicBusinessHour(clinic_id=clinic_id, **value) for value in values)

    def list_rooms(self, clinic_id: UUID, *, active_only: bool = False):
        query = self.session.query(ClinicRoom).filter_by(clinic_id=clinic_id)
        if active_only:
            query = query.filter(ClinicRoom.is_active.is_(True))
        return query.order_by(ClinicRoom.name).all()

    def get_room(self, clinic_id: UUID, room_id: UUID):
        return self.session.query(ClinicRoom).filter_by(clinic_id=clinic_id, id=room_id).first()

    def add_room(self, room: ClinicRoom) -> None:
        self.session.add(room)

    def list_availability(self, clinic_id: UUID, *, staff_member_id: UUID | None = None):
        query = self.session.query(DoctorAvailability).filter_by(clinic_id=clinic_id)
        if staff_member_id:
            query = query.filter(DoctorAvailability.staff_member_id == staff_member_id)
        return query.order_by(DoctorAvailability.staff_member_id, DoctorAvailability.weekday, DoctorAvailability.starts_at).all()

    def list_active_doctors(self, clinic_id: UUID):
        return self.session.query(StaffMember).join(UserProfile, UserProfile.id == StaffMember.auth_user_id).join(
            ClinicMembership,
            (ClinicMembership.user_id == UserProfile.id) & (ClinicMembership.clinic_id == clinic_id),
        ).filter(
            StaffMember.clinic_id == clinic_id,
            StaffMember.role == "doctor",
            StaffMember.is_active.is_(True),
            UserProfile.is_active.is_(True),
            UserProfile.deleted_at.is_(None),
            ClinicMembership.role == "doctor",
            ClinicMembership.status == "active",
        ).order_by(StaffMember.full_name).all()

    def get_availability(self, clinic_id: UUID, availability_id: UUID):
        return self.session.query(DoctorAvailability).filter_by(clinic_id=clinic_id, id=availability_id).first()

    def list_availability_for_date(self, clinic_id: UUID, staff_member_id: UUID, day: date):
        return self.session.query(DoctorAvailability).filter(
            DoctorAvailability.clinic_id == clinic_id,
            DoctorAvailability.staff_member_id == staff_member_id,
            DoctorAvailability.weekday == day.weekday(),
            DoctorAvailability.is_active.is_(True),
            DoctorAvailability.effective_from <= day,
            or_(DoctorAvailability.effective_to.is_(None), DoctorAvailability.effective_to >= day),
        ).order_by(DoctorAvailability.starts_at).all()

    def add_availability(self, availability: DoctorAvailability) -> None:
        self.session.add(availability)

    def setup_counts(self, clinic_id: UUID) -> dict[str, int]:
        return {
            "patients": self.session.query(func.count(Patient.id)).filter_by(clinic_id=clinic_id).scalar() or 0,
            "active_staff": self.session.query(func.count(ClinicMembership.id)).filter(
                ClinicMembership.clinic_id == clinic_id,
                ClinicMembership.status == "active",
                ClinicMembership.role.in_(("clinic_admin", "doctor", "nurse", "receptionist", "billing_staff")),
            ).scalar() or 0,
            "doctors": self.session.query(func.count(StaffMember.id)).filter_by(clinic_id=clinic_id, role="doctor", is_active=True).scalar() or 0,
            "rooms": self.session.query(func.count(ClinicRoom.id)).filter_by(clinic_id=clinic_id, is_active=True).scalar() or 0,
            "availability_rules": self.session.query(func.count(DoctorAvailability.id)).filter_by(clinic_id=clinic_id, is_active=True).scalar() or 0,
            "imported_jobs": self.session.query(func.count(PatientImportJob.id)).filter_by(clinic_id=clinic_id, status="completed").scalar() or 0,
        }

    def overlaps(self, clinic_id: UUID, starts_at, ends_at, *, staff_member_id: UUID | None = None, room_id: UUID | None = None, patient_id: UUID | None = None, exclude_appointment_id: UUID | None = None) -> bool:
        query = self.session.query(Appointment.id).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.status.notin_(("cancelled", "completed", "no_show", "void")),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        predicates = []
        if staff_member_id is not None:
            predicates.append(Appointment.assigned_staff_id == staff_member_id)
        if room_id is not None:
            predicates.append(Appointment.room_id == room_id)
        if patient_id is not None:
            predicates.append(Appointment.patient_id == patient_id)
        if not predicates:
            return False
        query = query.filter(or_(*predicates))
        if exclude_appointment_id:
            query = query.filter(Appointment.id != exclude_appointment_id)
        return query.first() is not None
