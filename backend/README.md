# Backend: CSRD carbon audit log

SQLAlchemy model and Alembic migrations for `carbon_audit_logs`, the
append-only table that stores every carbon calculation with its evidence.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your Supabase connection string
export $(cat .env | xargs)
alembic upgrade head
```

Use Supabase's direct connection or session pooler (port 5432) for migrations.

## What the table guarantees

| Requirement | How |
|---|---|
| Fast dashboard reads | Composite index `(company_id, calculated_at DESC)` plus `calculated_at` index |
| Exact, reproducible math | `NUMERIC` instead of float; `api_version` + full Climatiq factor in `calculation_metadata` |
| Evidence chain | `source_type`, `source_file_ref` (Storage path, not an expiring signed URL), `source_file_sha256` |
| Tamper resistance | Trigger rejects `UPDATE`, `DELETE`, `TRUNCATE`; corrections are new rows with `supersedes_id` |
| Valid data only | Check constraints on `scope`, `source_type`, `confidence_score`, non-negative amounts |
| No public exposure | Row Level Security enabled; Supabase's anon/authenticated roles see nothing until you add policies |

## Tests

Runs the migration up and down against a throwaway database:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/carbon_test pytest
```
