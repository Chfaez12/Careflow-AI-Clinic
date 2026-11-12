"""Billing claim data access."""

from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.patient import Patient


class ClaimRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_clinic(
        self,
        clinic_id: UUID,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[Claim, Patient]]:
        query = self.session.query(Claim, Patient).join(Patient, Patient.id == Claim.patient_id).filter(
            Claim.clinic_id == clinic_id,
            Patient.clinic_id == clinic_id,
        )
        if status:
            query = query.filter(Claim.status == status)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Claim.payer_claim_id.ilike(term),
                Claim.payer_name.ilike(term),
            ))
        return query.order_by(Claim.created_at.desc()).limit(limit).offset(offset).all()

    def get(self, clinic_id: UUID, claim_id: UUID) -> Claim | None:
        return self.session.query(Claim).filter_by(clinic_id=clinic_id, id=claim_id).first()

    def summary(self, clinic_id: UUID) -> dict:
        counts = dict(self.session.query(Claim.status, func.count(Claim.id)).filter_by(
            clinic_id=clinic_id,
        ).group_by(Claim.status).all())
        total_amount = self.session.query(func.coalesce(func.sum(Claim.amount), 0)).filter_by(
            clinic_id=clinic_id,
        ).scalar()
        return {"claim_counts": counts, "total_claim_amount": total_amount}

    def add(self, claim: Claim) -> None:
        self.session.add(claim)
