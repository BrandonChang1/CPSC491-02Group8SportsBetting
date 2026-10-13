# Sprint 3 Data Test Execution

## Purpose

The Sprint 3 Data & Storage regression suite validates database
integrity, ingestion idempotency, and modeling dataset requirements.

## Local Setup

A PostgreSQL test database is required for database integration tests.

Set `DATABASE_URL` in `.env`.

Example:

`DATABASE_URL=postgresql://user:password@localhost:5432/sports_betting_test`

Run database migrations:

`node database/migrate.js`

## Seed Deterministic Test Data

From the project root:

`psql "$DATABASE_URL" -f tests/fixtures/seed_ci_database.sql`

On Windows PowerShell:

`psql $env:DATABASE_URL -f tests/fixtures/seed_ci_database.sql`

## Run Sprint 3 Tests

`python -m pytest tests/test_database_integrity.py tests/test_ingestion_idempotency.py tests/test_modeling_dataset_validation.py -v`

## Run Full Python Test Suite

`python -m pytest -v`

## Linting

Check:

`ruff check . --exclude ml,.venv,node_modules,.git,.github,venv,dist,build,__pycache__`

Automatically fix supported lint issues locally:

`ruff check --fix . --exclude ml,.venv,node_modules,.git,.github,venv,dist,build,__pycache__`

## CI Environment

GitHub Actions provisions PostgreSQL automatically and supplies the
`DATABASE_URL` environment variable.

The CI workflow:

1. Starts PostgreSQL.
2. Runs migrations.
3. Loads deterministic test data.
4. Runs the Sprint 3 data regression suite.
5. Runs the remaining project tests.

No NBA API request is required for the Sprint 3 regression tests.