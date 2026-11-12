"""Link signed-note corrections to immutable originals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261111_signed_note_amendments"
down_revision = "20261110_patient_waitlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinical_notes", sa.Column("amends_note_id", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
    op.add_column("clinical_notes", sa.Column("amendment_reason", sa.Text(), nullable=True), schema="public")
    op.create_foreign_key(
        "fk_clinical_notes_amends_note_id_clinical_notes",
        "clinical_notes", "clinical_notes", ["amends_note_id"], ["id"],
        ondelete="SET NULL", source_schema="public", referent_schema="public",
    )
    op.create_index("ix_clinical_notes_amends_note_id", "clinical_notes", ["amends_note_id"], schema="public")


def downgrade() -> None:
    op.drop_index("ix_clinical_notes_amends_note_id", table_name="clinical_notes", schema="public")
    op.drop_constraint("fk_clinical_notes_amends_note_id_clinical_notes", "clinical_notes", type_="foreignkey", schema="public")
    op.drop_column("clinical_notes", "amendment_reason", schema="public")
    op.drop_column("clinical_notes", "amends_note_id", schema="public")
