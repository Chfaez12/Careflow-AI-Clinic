from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class Appointment(Base):
    __tablename__="appointments"
    __table_args__=(
        Index("ix_appointments_clinic_start","clinic_id","starts_at"),
        UniqueConstraint("clinic_id", "idempotency_key", name="uq_appointments_clinic_idempotency_key"),
    )
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="RESTRICT"),index=True,nullable=False)
    assigned_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    room_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinic_rooms.id",ondelete="SET NULL"),index=True)
    idempotency_key: Mapped[str|None]=mapped_column(String(100))
    request_fingerprint: Mapped[str|None]=mapped_column(String(64))
    starts_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True,nullable=False)
    ends_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="scheduled",nullable=False)
    reason: Mapped[str|None]=mapped_column(Text)
    source: Mapped[str]=mapped_column(String(30),default="staff",nullable=False)
    cancellation_reason: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    patient=relationship("Patient",back_populates="appointments")
