"""Allow patient-free, direct staff messages."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261109_staff_direct_messaging"
down_revision = "20261108_import_setup_scheduling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "messages", "patient_id", existing_type=postgresql.UUID(as_uuid=True),
        nullable=True, schema="public",
    )
    op.add_column(
        "messages",
        sa.Column("recipient_staff_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_messages_recipient_staff_id_staff_members", "messages", "staff_members",
        ["recipient_staff_id"], ["id"], ondelete="SET NULL",
        source_schema="public", referent_schema="public",
    )
    op.create_index(
        "ix_messages_clinic_staff_conversation", "messages",
        ["clinic_id", "channel", "sender_staff_id", "recipient_staff_id", "created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_messages_clinic_staff_conversation", table_name="messages", schema="public")
    op.drop_constraint(
        "fk_messages_recipient_staff_id_staff_members", "messages",
        type_="foreignkey", schema="public",
    )
    op.drop_column("messages", "recipient_staff_id", schema="public")
    # Existing standalone staff messages have no patient; downgrade cannot safely restore NOT NULL.
