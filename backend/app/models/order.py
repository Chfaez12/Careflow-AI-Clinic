from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class Order(Base):
    __tablename__="orders"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="RESTRICT"),index=True,nullable=False)
    visit_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id",ondelete="SET NULL"),index=True)
    created_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    order_type: Mapped[str]=mapped_column(String(30),nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="draft",nullable=False)
    details: Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    notes: Mapped[str|None]=mapped_column(Text)
    signed_by_staff_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="SET NULL"))
    signed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
