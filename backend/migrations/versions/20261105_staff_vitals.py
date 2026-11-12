"""Add nurse-recorded patient vital observations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261105_staff_vitals"
down_revision = "20261104_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_vitals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_by_staff_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blood_pressure_systolic", sa.SmallInteger(), nullable=True),
        sa.Column("blood_pressure_diastolic", sa.SmallInteger(), nullable=True),
        sa.Column("heart_rate", sa.SmallInteger(), nullable=True),
        sa.Column("respiratory_rate", sa.SmallInteger(), nullable=True),
        sa.Column("temperature_c", sa.Numeric(4, 1), nullable=True),
        sa.Column("oxygen_saturation", sa.SmallInteger(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column("height_cm", sa.Numeric(5, 2), nullable=True),
        sa.Column("pain_score", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("heart_rate IS NULL OR heart_rate BETWEEN 20 AND 250", name="valid_heart_rate"),
        sa.CheckConstraint("respiratory_rate IS NULL OR respiratory_rate BETWEEN 5 AND 80", name="valid_respiratory_rate"),
        sa.CheckConstraint("oxygen_saturation IS NULL OR oxygen_saturation BETWEEN 50 AND 100", name="valid_oxygen_saturation"),
        sa.CheckConstraint("pain_score IS NULL OR pain_score BETWEEN 0 AND 10", name="valid_pain_score"),
        sa.CheckConstraint("blood_pressure_systolic IS NULL OR blood_pressure_systolic BETWEEN 40 AND 300", name="valid_systolic"),
        sa.CheckConstraint("blood_pressure_diastolic IS NULL OR blood_pressure_diastolic BETWEEN 20 AND 200", name="valid_diastolic"),
        sa.CheckConstraint("temperature_c IS NULL OR temperature_c BETWEEN 25 AND 45", name="valid_temperature_c"),
        sa.CheckConstraint("weight_kg IS NULL OR weight_kg BETWEEN 0.01 AND 500", name="valid_weight_kg"),
        sa.CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 0.01 AND 250", name="valid_height_cm"),
        sa.CheckConstraint("(blood_pressure_systolic IS NULL) = (blood_pressure_diastolic IS NULL)", name="complete_blood_pressure"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], name="fk_patient_vitals_clinic_id_clinics", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name="fk_patient_vitals_patient_id_patients", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], name="fk_patient_vitals_visit_id_visits", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_staff_id"], ["staff_members.id"], name="fk_patient_vitals_recorded_by_staff_id_staff_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_patient_vitals"),
        schema="public",
    )
    op.create_index("ix_patient_vitals_clinic_id", "patient_vitals", ["clinic_id"], schema="public")
    op.create_index("ix_patient_vitals_patient_id", "patient_vitals", ["patient_id"], schema="public")
    op.create_index("ix_patient_vitals_visit_id", "patient_vitals", ["visit_id"], schema="public")
    op.create_index(
        "ix_patient_vitals_clinic_patient_recorded",
        "patient_vitals",
        ["clinic_id", "patient_id", "recorded_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_patient_vitals_clinic_patient_recorded", table_name="patient_vitals", schema="public")
    op.drop_index("ix_patient_vitals_visit_id", table_name="patient_vitals", schema="public")
    op.drop_index("ix_patient_vitals_patient_id", table_name="patient_vitals", schema="public")
    op.drop_index("ix_patient_vitals_clinic_id", table_name="patient_vitals", schema="public")
    op.drop_table("patient_vitals", schema="public")
