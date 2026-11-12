from datetime import date, time
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, SmallInteger, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        UniqueConstraint("clinic_id", "staff_member_id", "weekday", "starts_at", "effective_from", name="uq_doctor_availability_period"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="valid_availability_weekday"),
        CheckConstraint("ends_at > starts_at", name="valid_availability_interval"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="valid_availability_dates"),
        Index("ix_doctor_availability_clinic_staff_day", "clinic_id", "staff_member_id", "weekday", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    staff_member_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    starts_at: Mapped[time] = mapped_column(Time, nullable=False)
    ends_at: Mapped[time] = mapped_column(Time, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
