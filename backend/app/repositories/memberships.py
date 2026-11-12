"""Database access for tenant membership records."""

from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.clinic_membership import ClinicMembership
from app.models.user import UserProfile


class MembershipRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_user(self, user_id: UUID) -> list[ClinicMembership]:
        return self.session.query(ClinicMembership).filter(
            ClinicMembership.user_id == user_id
        ).all()

    def get_for_user_and_clinic(
        self,
        user_id: UUID,
        clinic_id: UUID,
    ) -> ClinicMembership | None:
        return (
            self.session.query(ClinicMembership)
            .options(joinedload(ClinicMembership.user))
            .filter_by(user_id=user_id, clinic_id=clinic_id)
            .first()
        )

    def list_clinic_members(self, clinic_id: UUID) -> list[tuple[ClinicMembership, UserProfile]]:
        return (
            self.session.query(ClinicMembership, UserProfile)
            .join(UserProfile, UserProfile.id == ClinicMembership.user_id)
            .filter(ClinicMembership.clinic_id == clinic_id)
            .order_by(ClinicMembership.created_at.desc())
            .all()
        )

    def add(self, membership: ClinicMembership) -> None:
        self.session.add(membership)

    def add_all(self, memberships: list[ClinicMembership]) -> None:
        self.session.add_all(memberships)

    def delete(self, membership: ClinicMembership) -> None:
        self.session.delete(membership)
