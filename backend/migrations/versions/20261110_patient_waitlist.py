"""Add patient waitlist entries and slot offers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261110_patient_waitlist"
down_revision = "20261109_staff_direct_messaging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_staff_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("earliest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="waiting", nullable=False),
        sa.Column("offered_appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("latest_at > earliest_at", name="valid_waitlist_window"),
        sa.CheckConstraint("status IN ('waiting', 'offered', 'booked', 'cancelled', 'expired')", name="valid_waitlist_status"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_staff_member_id"], ["staff_members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["offered_appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_index("ix_waitlist_entries_clinic_id", "waitlist_entries", ["clinic_id"], schema="public")
    op.create_index("ix_waitlist_entries_patient_id", "waitlist_entries", ["patient_id"], schema="public")
    op.create_index("ix_waitlist_clinic_status_window", "waitlist_entries", ["clinic_id", "status", "earliest_at", "latest_at"], schema="public")


def downgrade() -> None:
    op.drop_index("ix_waitlist_clinic_status_window", table_name="waitlist_entries", schema="public")
    op.drop_index("ix_waitlist_entries_patient_id", table_name="waitlist_entries", schema="public")
    op.drop_index("ix_waitlist_entries_clinic_id", table_name="waitlist_entries", schema="public")
    op.drop_table("waitlist_entries", schema="public")
