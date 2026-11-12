from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class AuditEvent(Base):
    __tablename__="audit_events"
    __table_args__=(Index("ix_audit_events_clinic_created","clinic_id","created_at"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    actor_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    actor_user_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),ForeignKey("users.id",ondelete="SET NULL"),index=True)
    patient_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="SET NULL"))
    action: Mapped[str]=mapped_column(String(100),nullable=False)
    resource_type: Mapped[str]=mapped_column(String(100),nullable=False)
    resource_id: Mapped[str|None]=mapped_column(String(100))
    ip_address: Mapped[str|None]=mapped_column(String(45))
    details: Mapped[dict|None]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
