from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class Claim(Base):
    __tablename__="claims"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="RESTRICT"),index=True,nullable=False)
    visit_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id",ondelete="SET NULL"),index=True)
    payer_name: Mapped[str|None]=mapped_column(String(200))
    payer_claim_id: Mapped[str|None]=mapped_column(String(100),index=True)
    status: Mapped[str]=mapped_column(String(30),default="draft",nullable=False)
    diagnosis_codes: Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    procedure_codes: Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    amount: Mapped[float|None]=mapped_column(Numeric(12,2))
    rejection_reason: Mapped[str|None]=mapped_column(Text)
    submitted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
