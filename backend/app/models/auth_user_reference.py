"""Metadata-only reference to the Supabase-managed Auth user table."""

from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import Base


auth_users_table = Table(
    "users",
    Base.metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    schema="auth",
    info={"external_table": True},
)
