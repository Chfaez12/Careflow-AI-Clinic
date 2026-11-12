from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class Patient(Base):
    __tablename__="patients"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    external_patient_id: Mapped[str|None]=mapped_column(String(100),index=True)
    first_name: Mapped[str]=mapped_column(String(100),nullable=False)
    last_name: Mapped[str]=mapped_column(String(100),nullable=False)
    date_of_birth: Mapped[date|None]=mapped_column(Date)
    sex: Mapped[str|None]=mapped_column(String(30))
    phone: Mapped[str|None]=mapped_column(String(30),index=True)
    email: Mapped[str|None]=mapped_column(String(255))
    address: Mapped[str|None]=mapped_column(Text)
    emergency_contact_name: Mapped[str|None]=mapped_column(String(150))
    emergency_contact_phone: Mapped[str|None]=mapped_column(String(30))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)
    clinic=relationship("Clinic",back_populates="patients")
    appointments=relationship("Appointment",back_populates="patient")
    allergies=relationship("Allergy",back_populates="patient")
    medications=relationship("Medication",back_populates="patient")
    visits=relationship("Visit",back_populates="patient")
    messages=relationship("Message",back_populates="patient")
