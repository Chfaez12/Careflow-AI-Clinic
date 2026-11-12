from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class Message(Base):
    __tablename__="messages"
    __table_args__=(
        Index("ix_messages_clinic_status_created", "clinic_id", "status", "created_at"),
        Index("ix_messages_clinic_assigned_status_created", "clinic_id", "assigned_staff_id", "status", "created_at"),
        Index("ix_messages_clinic_channel_reply", "clinic_id", "channel", "reply_to_message_id"),
        Index("ix_messages_clinic_staff_conversation", "clinic_id", "channel", "sender_staff_id", "recipient_staff_id", "created_at"),
    )
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="CASCADE"),index=True)
    channel: Mapped[str]=mapped_column(String(30),default="portal",nullable=False)
    direction: Mapped[str]=mapped_column(String(20),default="inbound",nullable=False)
    body: Mapped[str]=mapped_column(Text,nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="needs_review",nullable=False)
    triage_level: Mapped[str|None]=mapped_column(String(30))
    assigned_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    sender_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    recipient_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    reply_to_message_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("messages.id",ondelete="SET NULL"))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    reviewed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    reviewed_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    patient=relationship("Patient",back_populates="messages")
