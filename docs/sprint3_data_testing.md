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

## Data Pipeline Anomaly Tests

After migrations and seeding, run from the project root:

`python -m pytest tests/test_pipeline_anomalies.py -v`

The suite audits the database configured by `DATABASE_URL` for:

- Duplicate player/game keys and duplicate date/home/away game identities.
- Missing required stats, negative counts, non-finite numeric values, and percentages outside 0–1.
- Made shots exceeding attempts, inconsistent three-point totals, and points or rebounds that disagree with their components.
- Missing games, invalid game teams, and opponent/home-away assignments that disagree with the game.

Audit failures name the check and offending record identities. An empty database
fails rather than giving a misleading pass. Optional shooting fields are checked
when present; first-game NULL rolling averages, negative plus/minus, and overtime
minutes remain valid. These are consistency checks, not statistical outlier or
ingestion-volume monitoring.

The suite also injects known anomalies into temporary, unconstrained copies of the
tables to prove detection, and checks that valid records pass. These copies shadow
the real tables only within each test connection and are always rolled back.
Stored-data audits run in read-only transactions. The test role needs TEMP
privileges on the database and SELECT on `public.games` and `public.player_game_stats`.

Pytest returns exit code 0 on success and a nonzero code on failures or setup
errors, including a missing `DATABASE_URL`. The command can be run repeatedly
without modifying stored records or calling ESPN. CI runs it immediately after
seeding and uploads `test-results/pipeline-anomalies.xml` with the test artifacts.
