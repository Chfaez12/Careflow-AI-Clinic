"""Convert all application entity IDs and foreign keys to UUID.

Revision ID: 20261103_uuid_ids
Revises: 20261102_users
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261103_uuid_ids"
down_revision = "017159b3f954"
branch_labels = None
depends_on = None


TABLES = (
    "clinics", "outbox_events", "patients", "staff_members", "allergies",
    "appointments", "audit_events", "care_team_assignments", "medications",
    "messages", "visits", "ai_suggestions", "clinical_notes", "orders",
    "claims", "clinic_memberships",
)

# (table, column, referenced table); `id` is handled for every table above.
FOREIGN_KEYS = (
    ("outbox_events", "clinic_id", "clinics"),
    ("patients", "clinic_id", "clinics"),
    ("staff_members", "clinic_id", "clinics"),
    ("allergies", "clinic_id", "clinics"), ("allergies", "patient_id", "patients"),
    ("allergies", "recorded_by_staff_id", "staff_members"),
    ("appointments", "clinic_id", "clinics"), ("appointments", "patient_id", "patients"),
    ("appointments", "assigned_staff_id", "staff_members"),
    ("audit_events", "clinic_id", "clinics"), ("audit_events", "actor_staff_id", "staff_members"),
    ("audit_events", "patient_id", "patients"),
    ("care_team_assignments", "clinic_id", "clinics"),
    ("care_team_assignments", "patient_id", "patients"),
    ("care_team_assignments", "staff_member_id", "staff_members"),
    ("medications", "clinic_id", "clinics"), ("medications", "patient_id", "patients"),
    ("medications", "prescribed_by_staff_id", "staff_members"),
    ("messages", "clinic_id", "clinics"), ("messages", "patient_id", "patients"),
    ("messages", "assigned_staff_id", "staff_members"),
    ("messages", "reply_to_message_id", "messages"),
    ("messages", "reviewed_by_staff_id", "staff_members"),
    ("visits", "clinic_id", "clinics"), ("visits", "patient_id", "patients"),
    ("visits", "appointment_id", "appointments"),
    ("visits", "clinician_staff_id", "staff_members"),
    ("ai_suggestions", "clinic_id", "clinics"), ("ai_suggestions", "patient_id", "patients"),
    ("ai_suggestions", "visit_id", "visits"),
    ("ai_suggestions", "created_by_staff_id", "staff_members"),
    ("ai_suggestions", "decision_by_staff_id", "staff_members"),
    ("clinical_notes", "clinic_id", "clinics"), ("clinical_notes", "visit_id", "visits"),
    ("clinical_notes", "author_staff_id", "staff_members"),
    ("clinical_notes", "signed_by_staff_id", "staff_members"),
    ("orders", "clinic_id", "clinics"), ("orders", "patient_id", "patients"),
    ("orders", "visit_id", "visits"), ("orders", "created_by_staff_id", "staff_members"),
    ("orders", "signed_by_staff_id", "staff_members"),
    ("claims", "clinic_id", "clinics"), ("claims", "patient_id", "patients"),
    ("claims", "visit_id", "visits"),
    ("clinic_memberships", "clinic_id", "clinics"),
    ("clinic_memberships", "patient_id", "patients"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Remove existing references while the integer keys are replaced.
    for table in TABLES:
        for fk in inspector.get_foreign_keys(table, schema="public"):
            if fk["name"]:
                op.drop_constraint(fk["name"], table, type_="foreignkey", schema="public")

    op.create_table(
        "_uuid_id_map",
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("old_id", sa.BigInteger(), nullable=False),
        sa.Column("new_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("table_name", "old_id"),
        prefixes=["TEMPORARY"],
    )
    for table in TABLES:
        op.execute(sa.text(
            f'INSERT INTO _uuid_id_map (table_name, old_id, new_id) '
            f'SELECT :table_name, id, gen_random_uuid() FROM public."{table}"'
        ).bindparams(table_name=table))
        op.add_column(table, sa.Column("id_uuid", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
        op.execute(sa.text(
            f'UPDATE public."{table}" AS target SET id_uuid = mapping.new_id '
            f'FROM _uuid_id_map AS mapping WHERE mapping.table_name = :table_name AND mapping.old_id = target.id'
        ).bindparams(table_name=table))

    for table, column, parent in FOREIGN_KEYS:
        op.add_column(table, sa.Column(f"{column}_uuid", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
        op.execute(sa.text(
            f'UPDATE public."{table}" AS target SET "{column}_uuid" = mapping.new_id '
            f'FROM _uuid_id_map AS mapping WHERE mapping.table_name = :parent AND mapping.old_id = target."{column}"'
        ).bindparams(parent=parent))

    # Replacing each column cascades away indexes and unique constraints that
    # depend on integer identifiers; they are recreated after conversion.
    for table, column, _parent in FOREIGN_KEYS:
        op.drop_column(table, column, schema="public")
        op.alter_column(table, f"{column}_uuid", new_column_name=column, schema="public")
    for table in TABLES:
        op.drop_column(table, "id", schema="public")
        op.alter_column(table, "id_uuid", new_column_name="id", schema="public")
        op.alter_column(
            table, "id", nullable=False,
            server_default=sa.text("gen_random_uuid()"), schema="public",
        )
        op.create_primary_key(f"pk_{table}", table, ["id"], schema="public")

    # Auth user identifiers are UUIDs too; staff rows currently store these as text.
    op.alter_column(
        "staff_members", "auth_user_id",
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="auth_user_id::uuid",
        schema="public",
    )

    # Restore foreign keys, preserving the original delete behavior.
    for table, column, parent in FOREIGN_KEYS:
        ondelete = "SET NULL" if column.endswith("staff_id") or column in {
            "reply_to_message_id", "appointment_id",
        } or (table in {"clinic_memberships", "audit_events"} and column == "patient_id") \
          or (table in {"claims", "orders"} and column == "visit_id") else "CASCADE"
        if table == "appointments" and column == "patient_id" or table == "visits" and column == "patient_id" or table == "orders" and column == "patient_id" or table == "claims" and column == "patient_id":
            ondelete = "RESTRICT"
        if table == "audit_events" and column == "patient_id":
            ondelete = "SET NULL"
        op.create_foreign_key(
            f"fk_{table}_{column}_{parent}", table, parent, [column], ["id"],
            ondelete=ondelete, source_schema="public", referent_schema="public",
        )
    op.create_foreign_key(
        "fk_audit_events_actor_user_id_users", "audit_events", "users",
        ["actor_user_id"], ["id"], ondelete="SET NULL",
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_clinic_memberships_user_id_users", "clinic_memberships", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_clinic_memberships_invited_by_user_id_users", "clinic_memberships", "users",
        ["invited_by_user_id"], ["id"], ondelete="SET NULL",
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_staff_members_auth_user_id_users", "staff_members", "users",
        ["auth_user_id"], ["id"], ondelete="CASCADE",
        source_schema="public", referent_schema="public",
    )

    op.create_unique_constraint("uq_clinic_memberships_clinic_user", "clinic_memberships", ["clinic_id", "user_id"], schema="public")
    op.create_unique_constraint("uq_clinic_memberships_patient_id", "clinic_memberships", ["patient_id"], schema="public")
    op.create_unique_constraint("uq_care_team_patient_staff", "care_team_assignments", ["patient_id", "staff_member_id"], schema="public")
    op.create_unique_constraint("uq_staff_clinic_auth_user", "staff_members", ["clinic_id", "auth_user_id"], schema="public")

    required_foreign_keys = {
        (table, column) for table, column, _parent in FOREIGN_KEYS
        if column == "clinic_id" or (table, column) in {
            ("allergies", "patient_id"), ("appointments", "patient_id"),
            ("care_team_assignments", "patient_id"), ("care_team_assignments", "staff_member_id"),
            ("medications", "patient_id"), ("messages", "patient_id"),
            ("visits", "patient_id"), ("clinical_notes", "visit_id"),
            ("orders", "patient_id"), ("claims", "patient_id"),
        }
    }
    for table, column in required_foreign_keys:
        op.alter_column(table, column, nullable=False, schema="public")

    indexes = {
        "patients": ["clinic_id"], "staff_members": ["clinic_id"],
        "outbox_events": ["clinic_id"], "allergies": ["clinic_id", "patient_id"],
        "appointments": ["clinic_id", "patient_id"], "audit_events": ["clinic_id"],
        "care_team_assignments": ["clinic_id", "patient_id", "staff_member_id"],
        "medications": ["clinic_id", "patient_id"], "messages": ["clinic_id", "patient_id"],
        "visits": ["clinic_id", "patient_id", "appointment_id"],
        "ai_suggestions": ["clinic_id", "patient_id", "visit_id"],
        "clinical_notes": ["clinic_id", "visit_id"],
        "orders": ["clinic_id", "patient_id", "visit_id"],
        "claims": ["clinic_id", "patient_id", "visit_id"],
        "clinic_memberships": ["clinic_id"],
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column], schema="public")
    op.create_index("ix_appointments_clinic_start", "appointments", ["clinic_id", "starts_at"], schema="public")
    op.create_index("ix_audit_events_clinic_created", "audit_events", ["clinic_id", "created_at"], schema="public")
    op.create_index("ix_messages_clinic_status_created", "messages", ["clinic_id", "status", "created_at"], schema="public")
    op.create_index("ix_visits_clinic_patient_started", "visits", ["clinic_id", "patient_id", "started_at"], schema="public")
    op.create_index("ix_ai_suggestions_clinic_status", "ai_suggestions", ["clinic_id", "status"], schema="public")
    op.create_index("ix_clinical_notes_visit_version", "clinical_notes", ["visit_id", "version"], schema="public")
    op.drop_table("_uuid_id_map")


def downgrade() -> None:
    raise NotImplementedError("UUID entity identifiers cannot be safely downgraded to integers.")
