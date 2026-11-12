from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index("ix_waitlist_clinic_status_window", "clinic_id", "status", "earliest_at", "latest_at"),
        CheckConstraint("latest_at > earliest_at", name="valid_waitlist_window"),
        CheckConstraint("status IN ('waiting', 'offered', 'booked', 'cancelled', 'expired')", name="valid_waitlist_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    requested_staff_member_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id", ondelete="SET NULL"))
    earliest_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latest_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="waiting", nullable=False)
    offered_appointment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"))
    appointment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"))
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
