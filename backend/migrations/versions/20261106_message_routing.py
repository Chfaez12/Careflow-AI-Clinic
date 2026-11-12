"""Add message sender attribution and staff routing indexes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261106_message_routing"
down_revision = "20261105_staff_vitals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("sender_staff_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_messages_sender_staff_id_staff_members",
        "messages",
        "staff_members",
        ["sender_staff_id"],
        ["id"],
        ondelete="SET NULL",
        source_schema="public",
        referent_schema="public",
    )
    op.create_index(
        "ix_messages_clinic_assigned_status_created",
        "messages",
        ["clinic_id", "assigned_staff_id", "status", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_messages_clinic_channel_reply",
        "messages",
        ["clinic_id", "channel", "reply_to_message_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_messages_clinic_channel_reply", table_name="messages", schema="public")
    op.drop_index("ix_messages_clinic_assigned_status_created", table_name="messages", schema="public")
    op.drop_constraint("fk_messages_sender_staff_id_staff_members", "messages", type_="foreignkey", schema="public")
    op.drop_column("messages", "sender_staff_id", schema="public")
