from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class Medication(Base):
    __tablename__="medications"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="CASCADE"),index=True,nullable=False)
    name: Mapped[str]=mapped_column(String(200),nullable=False)
    rxnorm_code: Mapped[str|None]=mapped_column(String(50))
    dose: Mapped[str|None]=mapped_column(String(100))
    route: Mapped[str|None]=mapped_column(String(50))
    frequency: Mapped[str|None]=mapped_column(String(100))
    instructions: Mapped[str|None]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30),default="active",nullable=False)
    start_date: Mapped[date|None]=mapped_column(Date)
    end_date: Mapped[date|None]=mapped_column(Date)
    prescribed_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    patient=relationship("Patient",back_populates="medications")
