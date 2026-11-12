from uuid import UUID
"""Database access for clinic tenants."""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.clinic import Clinic


class ClinicRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, clinic_id: UUID) -> Clinic | None:
        return self.session.get(Clinic, clinic_id)

    def slug_exists(self, slug: str) -> bool:
        return self.session.query(Clinic.id).filter(Clinic.slug == slug).first() is not None

    def list_all(
        self,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Clinic]:
        query = self.session.query(Clinic)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(
                Clinic.name.ilike(pattern),
                Clinic.slug.ilike(pattern),
                Clinic.email.ilike(pattern),
            ))
        if is_active is not None:
            query = query.filter(Clinic.is_active.is_(is_active))
        return query.order_by(Clinic.created_at.desc()).offset(offset).limit(limit).all()

    def add(self, clinic: Clinic) -> None:
        self.session.add(clinic)
