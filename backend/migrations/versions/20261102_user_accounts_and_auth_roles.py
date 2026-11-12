"""Add Supabase-linked CareFlow users and tenant memberships.

Revision ID: 20261102_users
Revises: 472352f615b8
Create Date: 2026-11-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261102_users"
down_revision: Union[str, Sequence[str], None] = "472352f615b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=True),
        sa.Column("role", sa.String(30), server_default="user", nullable=False),
        sa.Column("is_super_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(is_super_admin = true AND role = 'super_admin') OR "
            "(is_super_admin = false AND role = 'user')",
            name="ck_users_valid_platform_role",
        ),
        sa.ForeignKeyConstraint(["id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "clinic_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('clinic_admin', 'doctor', 'nurse', 'receptionist', 'billing_staff', 'patient')",
            name="ck_clinic_memberships_valid_clinic_role",
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended')",
            name="ck_clinic_memberships_valid_membership_status",
        ),
        sa.CheckConstraint(
            "role = 'patient' OR patient_id IS NULL",
            name="ck_clinic_memberships_patient_membership_link",
        ),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_memberships"),
        sa.UniqueConstraint("clinic_id", "user_id", name="uq_clinic_memberships_clinic_user"),
        sa.UniqueConstraint("patient_id", name="uq_clinic_memberships_patient_id"),
    )
    op.create_index("ix_clinic_memberships_clinic_id", "clinic_memberships", ["clinic_id"])
    op.create_index("ix_clinic_memberships_user_id", "clinic_memberships", ["user_id"])

    op.add_column("audit_events", sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_audit_events_actor_user_id_users",
        "audit_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])

    # FastAPI is the only application-facing interface. Do not expose tenant
    # data through the Supabase Data API; the backend uses a server DB role and
    # enforces tenant membership in dependencies.
    api_tables = (
        "users", "clinic_memberships", "clinics", "staff_members", "patients",
        "appointments", "visits", "clinical_notes", "orders", "medications",
        "allergies", "messages", "care_team_assignments", "audit_events",
        "outbox_events", "claims", "ai_suggestions",
    )
    for table in api_tables:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")

    # A person can be staff at more than one clinic; uniqueness is per clinic.
    op.drop_index("ix_staff_members_auth_user_id", table_name="staff_members")
    op.create_index("ix_staff_members_auth_user_id", "staff_members", ["auth_user_id"], unique=False)
    op.create_unique_constraint(
        "uq_staff_clinic_auth_user", "staff_members", ["clinic_id", "auth_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_constraint("fk_audit_events_actor_user_id_users", "audit_events", type_="foreignkey")
    op.drop_column("audit_events", "actor_user_id")
    op.drop_constraint("uq_staff_clinic_auth_user", "staff_members", type_="unique")
    op.drop_index("ix_staff_members_auth_user_id", table_name="staff_members")
    op.create_index("ix_staff_members_auth_user_id", "staff_members", ["auth_user_id"], unique=True)
    op.drop_index("ix_clinic_memberships_user_id", table_name="clinic_memberships")
    op.drop_index("ix_clinic_memberships_clinic_id", table_name="clinic_memberships")
    op.drop_table("clinic_memberships")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
