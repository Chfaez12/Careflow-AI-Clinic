from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
class StaffMember(Base):
    __tablename__="staff_members"
    __table_args__ = (UniqueConstraint("clinic_id", "auth_user_id", name="uq_staff_clinic_auth_user"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    auth_user_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    full_name: Mapped[str]=mapped_column(String(150),nullable=False)
    email: Mapped[str]=mapped_column(String(255),index=True,nullable=False)
    phone: Mapped[str|None]=mapped_column(String(30))
    role: Mapped[str]=mapped_column(String(30),nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    clinic=relationship("Clinic",back_populates="staff_members")
