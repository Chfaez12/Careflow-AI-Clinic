from datetime import time
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClinicBusinessHour(Base):
    __tablename__ = "clinic_business_hours"
    __table_args__ = (
        UniqueConstraint("clinic_id", "weekday", name="uq_clinic_business_hours_clinic_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="valid_business_hour_weekday"),
        CheckConstraint("is_closed OR (opens_at IS NOT NULL AND closes_at > opens_at)", name="valid_business_hour_interval"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time)
    closes_at: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
