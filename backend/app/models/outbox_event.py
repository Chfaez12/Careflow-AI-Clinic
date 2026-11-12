from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class OutboxEvent(Base):
    __tablename__="outbox_events"
    __table_args__=(Index("ix_outbox_events_status_created","status","created_at"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    event_type: Mapped[str]=mapped_column(String(150),nullable=False)
    aggregate_type: Mapped[str]=mapped_column(String(100),nullable=False)
    aggregate_id: Mapped[str]=mapped_column(String(100),nullable=False)
    payload: Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    status: Mapped[str]=mapped_column(String(30),default="pending",nullable=False)
    attempts: Mapped[int]=mapped_column(default=0,nullable=False)
    last_error: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    processed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
