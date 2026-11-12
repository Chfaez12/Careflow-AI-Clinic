"""Add recoverable soft-delete markers for platform-managed users and clinics.

Revision ID: 20261104_soft_delete
Revises: 20261103_uuid_ids
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261104_soft_delete"
down_revision = "20261103_uuid_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="public")
    op.add_column("users", sa.Column("is_active_before_delete", sa.Boolean(), nullable=True), schema="public")
    op.add_column("users", sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
    op.create_foreign_key(
        "fk_users_deleted_by_user_id_users", "users", "users",
        ["deleted_by_user_id"], ["id"], ondelete="SET NULL",
        source_schema="public", referent_schema="public",
    )
    op.add_column("clinics", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="public")
    op.add_column("clinics", sa.Column("is_active_before_delete", sa.Boolean(), nullable=True), schema="public")
    op.add_column("clinics", sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
    op.create_foreign_key(
        "fk_clinics_deleted_by_user_id_users", "clinics", "users",
        ["deleted_by_user_id"], ["id"], ondelete="SET NULL",
        source_schema="public", referent_schema="public",
    )


def downgrade() -> None:
    op.drop_constraint("fk_clinics_deleted_by_user_id_users", "clinics", type_="foreignkey", schema="public")
    op.drop_column("clinics", "deleted_by_user_id", schema="public")
    op.drop_column("clinics", "is_active_before_delete", schema="public")
    op.drop_column("clinics", "deleted_at", schema="public")
    op.drop_constraint("fk_users_deleted_by_user_id_users", "users", type_="foreignkey", schema="public")
    op.drop_column("users", "deleted_by_user_id", schema="public")
    op.drop_column("users", "is_active_before_delete", schema="public")
    op.drop_column("users", "deleted_at", schema="public")
