from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Clinic(Base):
    __tablename__="clinics"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    name: Mapped[str]=mapped_column(String(150),nullable=False)
    slug: Mapped[str]=mapped_column(String(100),unique=True,index=True,nullable=False)
    email: Mapped[str]=mapped_column(String(255),index=True,nullable=False)
    phone: Mapped[str|None]=mapped_column(String(30))
    address: Mapped[str|None]=mapped_column(Text)
    timezone: Mapped[str]=mapped_column(String(64),default="UTC",nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    deleted_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    is_active_before_delete: Mapped[bool | None]=mapped_column(Boolean)
    deleted_by_user_id: Mapped[UUID | None]=mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)
    staff_members=relationship("StaffMember",back_populates="clinic")
    patients=relationship("Patient",back_populates="clinic")
