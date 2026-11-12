from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PatientVital(Base):
    __tablename__ = "patient_vitals"
    __table_args__ = (
        Index("ix_patient_vitals_clinic_patient_recorded", "clinic_id", "patient_id", "recorded_at"),
        CheckConstraint("heart_rate IS NULL OR heart_rate BETWEEN 20 AND 250", name="valid_heart_rate"),
        CheckConstraint("respiratory_rate IS NULL OR respiratory_rate BETWEEN 5 AND 80", name="valid_respiratory_rate"),
        CheckConstraint("oxygen_saturation IS NULL OR oxygen_saturation BETWEEN 50 AND 100", name="valid_oxygen_saturation"),
        CheckConstraint("pain_score IS NULL OR pain_score BETWEEN 0 AND 10", name="valid_pain_score"),
        CheckConstraint("blood_pressure_systolic IS NULL OR blood_pressure_systolic BETWEEN 40 AND 300", name="valid_systolic"),
        CheckConstraint("blood_pressure_diastolic IS NULL OR blood_pressure_diastolic BETWEEN 20 AND 200", name="valid_diastolic"),
        CheckConstraint("temperature_c IS NULL OR temperature_c BETWEEN 25 AND 45", name="valid_temperature_c"),
        CheckConstraint("weight_kg IS NULL OR weight_kg BETWEEN 0.01 AND 500", name="valid_weight_kg"),
        CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 0.01 AND 250", name="valid_height_cm"),
        CheckConstraint("(blood_pressure_systolic IS NULL) = (blood_pressure_diastolic IS NULL)", name="complete_blood_pressure"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True, nullable=False)
    visit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id", ondelete="RESTRICT"), index=True, nullable=False)
    recorded_by_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id", ondelete="SET NULL"))
    blood_pressure_systolic: Mapped[int | None] = mapped_column(SmallInteger)
    blood_pressure_diastolic: Mapped[int | None] = mapped_column(SmallInteger)
    heart_rate: Mapped[int | None] = mapped_column(SmallInteger)
    respiratory_rate: Mapped[int | None] = mapped_column(SmallInteger)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(4, 1))
    oxygen_saturation: Mapped[int | None] = mapped_column(SmallInteger)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2))
    height_cm: Mapped[float | None] = mapped_column(Numeric(5, 2))
    pain_score: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
