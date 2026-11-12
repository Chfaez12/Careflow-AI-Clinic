"""Database access for CareFlow user profiles."""

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import UserProfile


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: UUID) -> UserProfile | None:
        return self.session.get(UserProfile, user_id)

    def get_by_email(self, email: str) -> UserProfile | None:
        return self.session.query(UserProfile).filter(UserProfile.email == email).first()

    def list_all(
        self,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserProfile]:
        query = self.session.query(UserProfile)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(UserProfile.email.ilike(pattern), UserProfile.full_name.ilike(pattern)))
        if is_active is not None:
            query = query.filter(UserProfile.is_active.is_(is_active))
        return query.order_by(UserProfile.created_at.desc()).offset(offset).limit(limit).all()

    def has_super_admin(self) -> bool:
        return self.session.query(UserProfile.id).filter(
            UserProfile.is_super_admin.is_(True)
        ).first() is not None

    def has_other_active_super_admin(self, user_id: UUID) -> bool:
        return self.session.query(UserProfile.id).filter(
            UserProfile.is_super_admin.is_(True),
            UserProfile.is_active.is_(True),
            UserProfile.id != user_id,
        ).first() is not None

    def add(self, user: UserProfile) -> None:
        self.session.add(user)
