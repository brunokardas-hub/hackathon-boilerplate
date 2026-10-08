"""create carbon_audit_logs

Creates the append-only audit table for CSRD carbon records, with indexes on
company_id and calculated_at for dashboard queries.

Revision ID: 0001
Revises:
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carbon_audit_logs",
        # 1. Unique Identifiers & Location
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("company_id", sa.String(64), nullable=False),
        sa.Column("eu_region", sa.String(16), nullable=False),
        # 2. Chain of Custody & Evidence
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_file_ref", sa.String(1024), nullable=True),
        sa.Column("source_file_sha256", sa.String(64), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True),
        # 3. Raw Activity Data
        sa.Column("activity_id", sa.String(255), nullable=False),
        sa.Column("raw_amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("raw_unit", sa.String(32), nullable=False),
        # 4. The Carbon Math
        sa.Column("co2e_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("scope", sa.Integer(), nullable=False),
        # 5. Temporal Trackers & System Metadata
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("api_version", sa.String(32), nullable=False),
        sa.Column("calculation_metadata", postgresql.JSONB(), nullable=True),
        # 6. Corrections
        sa.Column(
            "supersedes_id",
            sa.Integer(),
            sa.ForeignKey("carbon_audit_logs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.CheckConstraint("scope IN (1, 2, 3)", name="ck_carbon_audit_logs_scope"),
        sa.CheckConstraint(
            "source_type IN ('pdf_invoice', 'api_integration', 'smart_meter_api', 'manual')",
            name="ck_carbon_audit_logs_source_type",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_carbon_audit_logs_confidence_score",
        ),
        sa.CheckConstraint("raw_amount >= 0", name="ck_carbon_audit_logs_raw_amount"),
        sa.CheckConstraint("co2e_kg >= 0", name="ck_carbon_audit_logs_co2e_kg"),
    )

    # Dashboard: one company's records, newest first. The leading company_id
    # column also serves lookups by company_id alone.
    op.create_index(
        "ix_carbon_audit_logs_company_id_calculated_at",
        "carbon_audit_logs",
        ["company_id", sa.text("calculated_at DESC")],
    )
    # Reporting-period queries across companies.
    op.create_index("ix_carbon_audit_logs_calculated_at", "carbon_audit_logs", ["calculated_at"])
    op.create_index("ix_carbon_audit_logs_supersedes_id", "carbon_audit_logs", ["supersedes_id"])

    # Append-only: auditors must be able to trust that no record was changed
    # after the fact. Corrections are inserted as new rows with supersedes_id.
    op.execute(
        """
        CREATE FUNCTION carbon_audit_logs_block_changes() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'carbon_audit_logs is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege',
                      HINT = 'Insert a new row with supersedes_id set to correct a record.';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER carbon_audit_logs_no_update_delete
        BEFORE UPDATE OR DELETE ON carbon_audit_logs
        FOR EACH ROW EXECUTE FUNCTION carbon_audit_logs_block_changes();
        """
    )
    op.execute(
        """
        CREATE TRIGGER carbon_audit_logs_no_truncate
        BEFORE TRUNCATE ON carbon_audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION carbon_audit_logs_block_changes();
        """
    )

    # Supabase exposes the public schema through its REST API. With RLS on and
    # no policies, the anon/authenticated roles see nothing; the FastAPI backend
    # connects as the table owner and is unaffected. Add per-company policies
    # here once the frontend reads directly through Supabase Auth.
    op.execute("ALTER TABLE carbon_audit_logs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("carbon_audit_logs")  # also drops its indexes and triggers
    op.execute("DROP FUNCTION IF EXISTS carbon_audit_logs_block_changes()")
