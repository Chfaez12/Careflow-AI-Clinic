from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class Visit(Base):
    __tablename__="visits"
    __table_args__=(Index("ix_visits_clinic_patient_started","clinic_id","patient_id","started_at"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="RESTRICT"),index=True,nullable=False)
    appointment_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("appointments.id",ondelete="SET NULL"),index=True)
    clinician_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    status: Mapped[str]=mapped_column(String(30),default="in_progress",nullable=False)
    chief_complaint: Mapped[str|None]=mapped_column(Text)
    recording_consent: Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    recording_consent_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    ended_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    patient=relationship("Patient",back_populates="visits")
    clinical_notes=relationship("ClinicalNote",back_populates="visit")
