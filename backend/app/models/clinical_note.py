from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class ClinicalNote(Base):
    __tablename__="clinical_notes"
    __table_args__=(Index("ix_clinical_notes_visit_version","visit_id","version"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    visit_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id",ondelete="CASCADE"),index=True,nullable=False)
    amends_note_id: Mapped[UUID | None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinical_notes.id",ondelete="SET NULL"),index=True)
    amendment_reason: Mapped[str | None]=mapped_column(Text)
    author_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    version: Mapped[int]=mapped_column(default=1,nullable=False)
    content: Mapped[str]=mapped_column(Text,nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="draft",nullable=False)
    signed_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    signed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    visit=relationship("Visit",back_populates="clinical_notes")
