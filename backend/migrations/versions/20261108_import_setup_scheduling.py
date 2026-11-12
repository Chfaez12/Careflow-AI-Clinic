"""Add import jobs, clinic setup, availability, rooms and booking idempotency."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261108_import_setup_scheduling"
down_revision = "20261107_medical_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
    op.add_column("appointments", sa.Column("idempotency_key", sa.String(length=100), nullable=True), schema="public")
    op.add_column("appointments", sa.Column("request_fingerprint", sa.String(length=64), nullable=True), schema="public")
    op.create_index("ix_appointments_room_id", "appointments", ["room_id"], schema="public")
    op.create_unique_constraint("uq_appointments_clinic_idempotency_key", "appointments", ["clinic_id", "idempotency_key"], schema="public")

    op.create_table(
        "clinic_business_hours",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="valid_business_hour_weekday"),
        sa.CheckConstraint("is_closed OR (opens_at IS NOT NULL AND closes_at > opens_at)", name="valid_business_hour_interval"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "weekday", name="uq_clinic_business_hours_clinic_weekday"),
        schema="public",
    )
    op.create_index("ix_clinic_business_hours_clinic_id", "clinic_business_hours", ["clinic_id"], schema="public")

    op.create_table(
        "clinic_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("room_type", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_clinic_rooms_clinic_name"),
        schema="public",
    )
    op.create_index("ix_clinic_rooms_clinic_id", "clinic_rooms", ["clinic_id"], schema="public")
    op.create_foreign_key("fk_appointments_room_id_clinic_rooms", "appointments", "clinic_rooms", ["room_id"], ["id"], ondelete="SET NULL", source_schema="public", referent_schema="public")

    op.create_table(
        "doctor_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="valid_availability_weekday"),
        sa.CheckConstraint("ends_at > starts_at", name="valid_availability_interval"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="valid_availability_dates"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_member_id"], ["staff_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "staff_member_id", "weekday", "starts_at", "effective_from", name="uq_doctor_availability_period"),
        schema="public",
    )
    op.create_index("ix_doctor_availability_clinic_id", "doctor_availability", ["clinic_id"], schema="public")
    op.create_index("ix_doctor_availability_staff_member_id", "doctor_availability", ["staff_member_id"], schema="public")
    op.create_index("ix_doctor_availability_clinic_staff_day", "doctor_availability", ["clinic_id", "staff_member_id", "weekday", "is_active"], schema="public")

    op.create_table(
        "patient_import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="uploaded", nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("processed_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_row", sa.Integer(), server_default="2", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        schema="public",
    )
    op.create_index("ix_patient_import_jobs_clinic_id", "patient_import_jobs", ["clinic_id"], schema="public")
    op.create_index("ix_patient_import_jobs_clinic_status_created", "patient_import_jobs", ["clinic_id", "status", "created_at"], schema="public")

    op.create_table(
        "patient_import_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("row_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["patient_import_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "row_number", "field", name="uq_patient_import_errors_job_row_field"),
        schema="public",
    )
    op.create_index("ix_patient_import_errors_clinic_id", "patient_import_errors", ["clinic_id"], schema="public")
    op.create_index("ix_patient_import_errors_job_row", "patient_import_errors", ["job_id", "row_number"], schema="public")

    for table in (
        "medical_conditions",
        "clinic_business_hours",
        "clinic_rooms",
        "doctor_availability",
        "patient_import_jobs",
        "patient_import_errors",
    ):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")


def downgrade() -> None:
    op.drop_index("ix_patient_import_errors_job_row", table_name="patient_import_errors", schema="public")
    op.drop_index("ix_patient_import_errors_clinic_id", table_name="patient_import_errors", schema="public")
    op.drop_table("patient_import_errors", schema="public")
    op.drop_index("ix_patient_import_jobs_clinic_status_created", table_name="patient_import_jobs", schema="public")
    op.drop_index("ix_patient_import_jobs_clinic_id", table_name="patient_import_jobs", schema="public")
    op.drop_table("patient_import_jobs", schema="public")
    op.drop_index("ix_doctor_availability_clinic_staff_day", table_name="doctor_availability", schema="public")
    op.drop_index("ix_doctor_availability_staff_member_id", table_name="doctor_availability", schema="public")
    op.drop_index("ix_doctor_availability_clinic_id", table_name="doctor_availability", schema="public")
    op.drop_table("doctor_availability", schema="public")
    op.drop_index("ix_clinic_rooms_clinic_id", table_name="clinic_rooms", schema="public")
    op.drop_table("clinic_rooms", schema="public")
    op.drop_index("ix_clinic_business_hours_clinic_id", table_name="clinic_business_hours", schema="public")
    op.drop_table("clinic_business_hours", schema="public")
    op.drop_constraint("uq_appointments_clinic_idempotency_key", "appointments", type_="unique", schema="public")
    op.drop_index("ix_appointments_room_id", table_name="appointments", schema="public")
    op.drop_constraint("fk_appointments_room_id_clinic_rooms", "appointments", type_="foreignkey", schema="public")
    op.drop_column("appointments", "request_fingerprint", schema="public")
    op.drop_column("appointments", "idempotency_key", schema="public")
    op.drop_column("appointments", "room_id", schema="public")
