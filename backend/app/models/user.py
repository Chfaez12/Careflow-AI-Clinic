from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserProfile(Base):
    """CareFlow profile linked one-to-one to Supabase Auth's auth.users row."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(is_super_admin = true AND role = 'super_admin') OR "
            "(is_super_admin = false AND role = 'user')",
            name="valid_platform_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active_before_delete: Mapped[bool | None] = mapped_column(Boolean)
    deleted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    memberships = relationship(
        "ClinicMembership",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ClinicMembership.user_id",
    )
