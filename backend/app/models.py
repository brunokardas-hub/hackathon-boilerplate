"""
Database models for EU CSRD-ready carbon accounting.

Every carbon calculation is stored as an immutable audit record: the evidence
it came from, the raw input, the emission factor used, and the result. Rows are
append-only (enforced by a database trigger, see the initial migration); a
correction is a new row that points at the row it replaces via `supersedes_id`.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


SOURCE_TYPES = ("pdf_invoice", "api_integration", "smart_meter_api", "manual")


class CarbonAuditLog(Base):
    """
    Defines the strict data retention requirements for EU CSRD carbon reporting.
    Saves inputs, outputs, and raw document proof for third-party auditors.
    """

    __tablename__ = "carbon_audit_logs"

    # 1. Unique Identifiers & Location
    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # ISO 3166-1 alpha-2 country code, optionally with a region suffix
    # (e.g. "NL", "DE", "ES-CT"). Determines the local grid emission factor.
    eu_region: Mapped[str] = mapped_column(String(16), nullable=False)

    # 2. Chain of Custody & Evidence (Audit Trail)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Storage object path (e.g. "invoices/<company_id>/2026/inv-123.pdf") in a
    # private Supabase Storage bucket. Store the path, not a signed URL: signed
    # URLs expire, the path stays valid and a fresh signed URL is minted on demand.
    source_file_ref: Mapped[str | None] = mapped_column(String(1024))
    # SHA-256 of the evidence file, proving the document was not altered later.
    source_file_sha256: Mapped[str | None] = mapped_column(String(64))
    # AI extraction confidence between 0 and 1 (e.g. 0.98); null for manual entries.
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # 3. Raw Activity Data (The Input)
    # Climatiq emission factor identifier (e.g. "electricity-supply_grid-source_residual_mix")
    activity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Numeric instead of Float: exact decimals, so totals reproduce to the gram.
    raw_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    raw_unit: Mapped[str] = mapped_column(String(32), nullable=False)  # "kWh", "l", "EUR"

    # 4. The Carbon Math (The Output)
    co2e_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    scope: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 Direct, 2 Electricity, 3 Supply chain

    # 5. Temporal Trackers & System Metadata
    # Server-side default so every row gets its own insert time from the database clock.
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Climatiq API version used (e.g. "v1"), kept as a column so auditors can filter on it.
    api_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Full emission factor details returned by Climatiq (factor value, source,
    # year, region, data_version, request payload) for exact reproduction later.
    calculation_metadata: Mapped[dict | None] = mapped_column(JSONB)

    # 6. Corrections: rows are never edited, a fix is a new row referencing the old one.
    supersedes_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("carbon_audit_logs.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        CheckConstraint("scope IN (1, 2, 3)", name="ck_carbon_audit_logs_scope"),
        CheckConstraint(
            "source_type IN (" + ", ".join(f"'{t}'" for t in SOURCE_TYPES) + ")",
            name="ck_carbon_audit_logs_source_type",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_carbon_audit_logs_confidence_score",
        ),
        CheckConstraint("raw_amount >= 0", name="ck_carbon_audit_logs_raw_amount"),
        CheckConstraint("co2e_kg >= 0", name="ck_carbon_audit_logs_co2e_kg"),
        # Dashboard query: one company's records, newest first. Also serves
        # lookups by company_id alone, so no separate company_id index is needed.
        Index("ix_carbon_audit_logs_company_id_calculated_at", "company_id", calculated_at.desc()),
        # Cross-company time-range queries (reporting periods, admin views).
        Index("ix_carbon_audit_logs_calculated_at", "calculated_at"),
        Index("ix_carbon_audit_logs_supersedes_id", "supersedes_id"),
    )

    def to_dict(self):
        """Serializes an entry for the frontend dashboard."""
        return {
            "id": self.id,
            "company_id": self.company_id,
            "eu_region": self.eu_region,
            "source": {
                "type": self.source_type,
                "file": self.source_file_ref,
                "sha256": self.source_file_sha256,
            },
            "input": {
                "activity_id": self.activity_id,
                "amount": _to_float(self.raw_amount),
                "unit": self.raw_unit,
            },
            "output": {"co2e_kg": _to_float(self.co2e_kg), "scope": f"Scope {self.scope}"},
            "audit": {
                "timestamp": self.calculated_at.isoformat() if self.calculated_at else None,
                "confidence": _to_float(self.confidence_score),
                "api_version": self.api_version,
                "supersedes_id": self.supersedes_id,
            },
        }


def _to_float(value):
    return float(value) if value is not None else None
