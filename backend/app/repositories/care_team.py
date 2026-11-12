"""Clinic-scoped care-team assignments."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.care_team_assignment import CareTeamAssignment
from app.models.clinic_membership import ClinicMembership
from app.models.patient import Patient
from app.models.staff_member import StaffMember
from app.models.user import UserProfile


class CareTeamRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_staff(self, clinic_id: UUID, staff_member_id: UUID) -> list[CareTeamAssignment]:
        return self.session.query(CareTeamAssignment).filter_by(
            clinic_id=clinic_id,
            staff_member_id=staff_member_id,
        ).all()

    def list_assignments(self, clinic_id: UUID, patient_id: UUID | None = None):
        query = self.session.query(CareTeamAssignment, StaffMember).join(
            StaffMember,
            (StaffMember.id == CareTeamAssignment.staff_member_id)
            & (StaffMember.clinic_id == clinic_id),
        ).filter(CareTeamAssignment.clinic_id == clinic_id)
        if patient_id is not None:
            query = query.filter(CareTeamAssignment.patient_id == patient_id)
        return query.order_by(StaffMember.full_name.asc()).all()

    def list_eligible_staff(self, clinic_id: UUID):
        return self.session.query(StaffMember).join(
            UserProfile, UserProfile.id == StaffMember.auth_user_id,
        ).join(
            ClinicMembership,
            (ClinicMembership.user_id == StaffMember.auth_user_id)
            & (ClinicMembership.clinic_id == clinic_id),
        ).filter(
            StaffMember.clinic_id == clinic_id,
            StaffMember.is_active.is_(True),
            StaffMember.role.in_(("doctor", "nurse")),
            UserProfile.is_active.is_(True),
            UserProfile.deleted_at.is_(None),
            ClinicMembership.status == "active",
            ClinicMembership.role == StaffMember.role,
        ).order_by(StaffMember.full_name.asc()).all()

    def list_patients_for_staff(self, clinic_id: UUID, staff_member_id: UUID) -> list[Patient]:
        return self.session.query(Patient).join(
            CareTeamAssignment,
            CareTeamAssignment.patient_id == Patient.id,
        ).filter(
            CareTeamAssignment.clinic_id == clinic_id,
            CareTeamAssignment.staff_member_id == staff_member_id,
            Patient.clinic_id == clinic_id,
        ).order_by(Patient.last_name, Patient.first_name).all()

    def has_assignment(self, clinic_id: UUID, patient_id: UUID, staff_member_id: UUID) -> bool:
        return self.session.query(CareTeamAssignment.id).filter_by(
            clinic_id=clinic_id,
            patient_id=patient_id,
            staff_member_id=staff_member_id,
        ).first() is not None

    def list_assigned_doctors(self, clinic_id: UUID, patient_id: UUID) -> list[StaffMember]:
        return self.session.query(StaffMember).join(
            CareTeamAssignment,
            CareTeamAssignment.staff_member_id == StaffMember.id,
        ).join(
            UserProfile,
            UserProfile.id == StaffMember.auth_user_id,
        ).join(
            ClinicMembership,
            (ClinicMembership.user_id == UserProfile.id)
            & (ClinicMembership.clinic_id == clinic_id),
        ).filter(
            CareTeamAssignment.clinic_id == clinic_id,
            CareTeamAssignment.patient_id == patient_id,
            StaffMember.clinic_id == clinic_id,
            StaffMember.role == "doctor",
            StaffMember.is_active.is_(True),
            UserProfile.is_active.is_(True),
            UserProfile.deleted_at.is_(None),
            ClinicMembership.role == "doctor",
            ClinicMembership.status == "active",
        ).order_by(StaffMember.full_name.asc()).all()

    def get_assigned_doctor(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        staff_member_id: UUID,
    ) -> StaffMember | None:
        return next(
            (item for item in self.list_assigned_doctors(clinic_id, patient_id)
             if item.id == staff_member_id),
            None,
        )

    def get(self, clinic_id: UUID, assignment_id: UUID) -> CareTeamAssignment | None:
        return self.session.query(CareTeamAssignment).filter_by(
            clinic_id=clinic_id,
            id=assignment_id,
        ).first()

    def add(self, assignment: CareTeamAssignment) -> None:
        self.session.add(assignment)

    def delete(self, assignment: CareTeamAssignment) -> None:
        self.session.delete(assignment)
