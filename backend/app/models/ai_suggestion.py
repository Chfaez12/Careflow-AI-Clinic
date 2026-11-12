from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class AISuggestion(Base):
    __tablename__="ai_suggestions"
    __table_args__=(Index("ix_ai_suggestions_clinic_status","clinic_id","status"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="CASCADE"),index=True)
    visit_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id",ondelete="CASCADE"),index=True)
    created_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    suggestion_type: Mapped[str]=mapped_column(String(50),nullable=False)
    content: Mapped[str]=mapped_column(Text,nullable=False)
    structured_data: Mapped[dict|None]=mapped_column(JSON)
    model_name: Mapped[str|None]=mapped_column(String(100))
    model_version: Mapped[str|None]=mapped_column(String(100))
    status: Mapped[str]=mapped_column(String(30),default="pending",nullable=False)
    decision_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    decision_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
