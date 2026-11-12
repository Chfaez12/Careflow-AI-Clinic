from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClinicRoom(Base):
    __tablename__ = "clinic_rooms"
    __table_args__ = (UniqueConstraint("clinic_id", "name", name="uq_clinic_rooms_clinic_name"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    room_type: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
