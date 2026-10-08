"""
Integration tests for the carbon_audit_logs migration and model.

Run against a throwaway PostgreSQL database (never production):
    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/carbon_test pytest
"""
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import CarbonAuditLog

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


def alembic(*args):
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


@pytest.fixture(scope="module")
def engine():
    alembic("downgrade", "base")
    alembic("upgrade", "head")
    url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    yield eng
    eng.dispose()
    alembic("downgrade", "base")


def make_log(**overrides):
    values = dict(
        company_id="acme-bv",
        eu_region="NL",
        source_type="pdf_invoice",
        source_file_ref="invoices/acme-bv/2026/inv-123.pdf",
        confidence_score=Decimal("0.98"),
        activity_id="electricity-supply_grid-source_residual_mix",
        raw_amount=Decimal("4500"),
        raw_unit="kWh",
        co2e_kg=Decimal("1912.5"),
        scope=2,
        api_version="v1",
        calculation_metadata={"emission_factor": {"region": "NL", "year": 2025}},
    )
    values.update(overrides)
    return CarbonAuditLog(**values)


def test_indexes_exist(engine):
    indexes = {ix["name"]: ix["column_names"] for ix in inspect(engine).get_indexes("carbon_audit_logs")}
    assert indexes["ix_carbon_audit_logs_company_id_calculated_at"][0] == "company_id"
    assert indexes["ix_carbon_audit_logs_calculated_at"] == ["calculated_at"]


def test_insert_and_serialize(engine):
    with Session(engine) as session:
        log = make_log()
        session.add(log)
        session.commit()
        session.refresh(log)
        data = log.to_dict()
    assert data["output"] == {"co2e_kg": 1912.5, "scope": "Scope 2"}
    assert data["audit"]["timestamp"] is not None
    assert data["audit"]["api_version"] == "v1"


def test_each_row_gets_its_own_timestamp(engine):
    with Session(engine) as session:
        first = make_log()
        session.add(first)
        session.commit()
        session.execute(text("SELECT pg_sleep(0.01)"))
        second = make_log()
        session.add(second)
        session.commit()
        assert second.calculated_at > first.calculated_at


@pytest.mark.parametrize(
    "overrides",
    [{"scope": 4}, {"source_type": "email"}, {"confidence_score": Decimal("1.5")}, {"co2e_kg": Decimal("-1")}],
)
def test_check_constraints(engine, overrides):
    with Session(engine) as session:
        session.add(make_log(**overrides))
        with pytest.raises(IntegrityError):
            session.commit()


def test_rows_cannot_be_updated_or_deleted(engine):
    with Session(engine) as session:
        log = make_log()
        session.add(log)
        session.commit()
        for statement in (
            "UPDATE carbon_audit_logs SET co2e_kg = 0 WHERE id = :id",
            "DELETE FROM carbon_audit_logs WHERE id = :id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                session.execute(text(statement), {"id": log.id})
            session.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(text("TRUNCATE carbon_audit_logs"))
        session.rollback()


def test_correction_supersedes_original(engine):
    with Session(engine) as session:
        original = make_log()
        session.add(original)
        session.commit()
        correction = make_log(co2e_kg=Decimal("1800"), supersedes_id=original.id)
        session.add(correction)
        session.commit()
        stored = session.scalars(select(CarbonAuditLog).where(CarbonAuditLog.supersedes_id == original.id)).one()
        assert stored.co2e_kg == Decimal("1800")
