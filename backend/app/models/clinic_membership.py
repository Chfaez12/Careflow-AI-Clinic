from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ClinicMembership(Base):
    """A user's role and status inside one clinic tenant."""

    __tablename__ = "clinic_memberships"
    __table_args__ = (
        UniqueConstraint("clinic_id", "user_id", name="uq_clinic_memberships_clinic_user"),
        CheckConstraint(
            "role IN ('clinic_admin', 'doctor', 'nurse', 'receptionist', 'billing_staff', 'patient')",
            name="valid_clinic_role",
        ),
        CheckConstraint("status IN ('invited', 'active', 'suspended')", name="valid_membership_status"),
        CheckConstraint("role = 'patient' OR patient_id IS NULL", name="patient_membership_link"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    patient_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), unique=True)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("UserProfile", back_populates="memberships", foreign_keys=[user_id])
