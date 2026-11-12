from uuid import UUID
"""Database access for clinic workflow staff records."""

from sqlalchemy.orm import Session

from app.models.staff_member import StaffMember


class StaffMemberRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_for_user(self, clinic_id: UUID, auth_user_id: UUID) -> StaffMember | None:
        return self.session.query(StaffMember).filter_by(
            clinic_id=clinic_id,
            auth_user_id=auth_user_id,
        ).first()

    def get_for_clinic(self, clinic_id: UUID, staff_member_id: UUID) -> StaffMember | None:
        return self.session.query(StaffMember).filter_by(
            clinic_id=clinic_id,
            id=staff_member_id,
        ).first()

    def list_message_recipients(self, clinic_id: UUID) -> list[StaffMember]:
        return self.session.query(StaffMember).filter(
            StaffMember.clinic_id == clinic_id,
            StaffMember.is_active.is_(True),
            StaffMember.role.in_(("doctor", "receptionist")),
        ).order_by(StaffMember.role.asc(), StaffMember.full_name.asc()).all()

    def list_internal_recipients(self, clinic_id: UUID) -> list[StaffMember]:
        return self.session.query(StaffMember).filter(
            StaffMember.clinic_id == clinic_id,
            StaffMember.is_active.is_(True),
        ).order_by(StaffMember.full_name.asc()).all()

    def add(self, member: StaffMember) -> None:
        self.session.add(member)

    def delete(self, member: StaffMember) -> None:
        self.session.delete(member)
