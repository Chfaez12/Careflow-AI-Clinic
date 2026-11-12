"""Add patient medical conditions for clinical charts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261107_medical_conditions"
down_revision = "20261106_message_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medical_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("code_system", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("onset_date", sa.Date(), nullable=True),
        sa.Column("resolved_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_staff_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'resolved', 'inactive')", name="valid_medical_condition_status"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_staff_id"], ["staff_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_index("ix_medical_conditions_clinic_id", "medical_conditions", ["clinic_id"], schema="public")
    op.create_index("ix_medical_conditions_patient_id", "medical_conditions", ["patient_id"], schema="public")
    op.create_index("ix_conditions_clinic_patient_status", "medical_conditions", ["clinic_id", "patient_id", "status"], schema="public")


def downgrade() -> None:
    op.drop_index("ix_conditions_clinic_patient_status", table_name="medical_conditions", schema="public")
    op.drop_index("ix_medical_conditions_patient_id", table_name="medical_conditions", schema="public")
    op.drop_index("ix_medical_conditions_clinic_id", table_name="medical_conditions", schema="public")
    op.drop_table("medical_conditions", schema="public")
