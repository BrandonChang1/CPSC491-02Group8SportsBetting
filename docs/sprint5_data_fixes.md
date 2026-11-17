# Sprint 5 Data Inconsistency Fixes and Pipeline Regression Tests (SCRUM-140)

## Review of the data-quality findings

Inputs reviewed on 2026-11-16:
- The automated data-quality report (SCRUM-136), on the development database and on a fresh CI-style database (migrations plus `tests/fixtures/seed_ci_database.sql`)
- `python -m data.processing.prediction_readiness`
- The manual source comparison `docs/evidence/cc7-2/manual-review-m02/`, which found 20 of 20 fields matching
- Extra read-only cross-row queries: per-game W/L, matchup and opponent agreement; legacy versus ESPN-offset player identities; roster team versus latest game team

| # | Finding | Impact | Disposition |
|---|---|---|---|
| 1 | `ingest_player_game_stats` computed `recent_minutes_avg` from only the ingested batch, ignoring games already stored. A new season's first game got `NULL` and the next four got averages that were too short. `database_ingestion.main` never recalculated afterwards. The backfill recalculated only once at the end, so seasons it had already committed stayed wrong until then, or for good if the run stopped early. | **High.** `recent_minutes_avg` is a served model input; wrong values change predictions and break the readiness contract. | **Fixed** (see below) |
| 2 | Player search ordered by name only, so same-name players (e.g. two "Mike James") had no defined order and could repeat or vanish across pages | Medium (API correctness) | Fixed in SCRUM-139; regression test added here |
| 3 | `tests/test_pipeline_anomalies.py` (35 stored-data anomaly tests) was ignored by CI's Python step and run nowhere else | Medium (no CI coverage) | **Fixed:** added to CI |
| 4 | ESPN box score entry without an athlete id failed whole seasons | High | Fixed earlier this sprint (`test_teammate_without_athlete_id_is_skipped`) |
| 5 | Retrieval failures and partial backfill batches | High | Fixed in SCRUM-138 (retries, per-season transaction) |
| 6 | 1 stat row with 0 minutes and 1 rebound (`1628396` / `0022400942`) | Low | Not a defect: minutes are whole numbers, so a stint under a minute rounds to 0. Stays a report warning. |
| 7 | 36 players whose `players.team_id` differs from the team in their latest stored game | Low | Intended: the roster team overrides historical affiliation (`test_roster_teams_override_history_and_survive_backfill`). Their latest stored games are from 2024-25. |
| 8 | 38 player names shared by more than one player ID | None | All are distinct historical players. No legacy/ESPN-offset pair refers to the same person, and the report's warning check passes for players with stats. |

The stored development data had no error-level inconsistencies. Finding 1 hadn't
corrupted it only because the last backfill reached its final full recalculation.
The defect was latent in every ingestion path except the incremental refresh.

## Fix for finding 1

In `data/ingestion/database_ingestion.py`, `ingest_player_game_stats` now
recalculates `recent_minutes_avg` from each affected player's **full stored
history** after its upserts. It uses `recalculate_recent_minutes_avg(connection,
player_id)` on the caller's connection, so inside the backfill's per-season
transaction the values are correct when the season commits.

Existing raw statistics aren't touched; only the derived average is recomputed,
using the same SQL the refresh already used. The incremental refresh's own
recalculation is kept and is now redundant but harmless. The backfill's final
full-table recalculation is kept as a safety net.

## Regression coverage added

| Test | Guards against |
|---|---|
| `tests/test_pipeline_regressions.py` (4, real PostgreSQL temp tables) | New-season batch ignoring stored games (autocommit and transactional paths); an older season arriving later; the report accepting ingested history. All 4 fail without the fix. |
| `tests/test_data_quality_report.py` (+2) | The report detects a wrong rolling average and cross-row conflicts (teammates' W/L, both sides winning, `@` with `is_home`) |
| `backend/tests/players.test.js` (+1) | Same-name players page in stable id order |
| `tests/test_ingestion_failure_logging.py` | Updated so the mock-connection row-failure test stubs the new post-processing call, as it already stubbed `refresh_player_team_ids` |

New data-quality report checks (category `consistency`, all error level):
- `recent_minutes_avg` matches the prior-5-game average
- teammates agree on result, matchup and opponent
- home and away sides have opposite results
- `vs.`/`@` agrees with `is_home`

## CI changes (`.github/workflows/ci.yml`)

- "Run Sprint 3 data regression tests" is now **"Run data pipeline regression tests"**. It adds `test_pipeline_anomalies.py` (previously never run), `test_pipeline_regressions.py` and `test_data_quality_report.py`. They're ignored in the catch-all Python step so nothing runs twice.
- New step **"Run data-quality report"** runs the read-only report against the seeded CI database, writes it to the job summary, and fails the job on any error-level check.

## Local verification (2026-11-16)

- Full Python suite: 355 passed. `ruff check` clean.
- CI simulation on a fresh database (migrate + seed, then each CI command in order):
  - data pipeline regression step: 77 passed
  - data-quality report: exit 0
  - remaining Python tests: 201 passed
  - backend: 76 passed, 1 failed
- The backend failure is `predictionsApi.test.js` ("returns the approved manifest's model_version"). It fails the same way on `main` without these changes, so this work didn't cause it. It's the model-serving path, not Data & Storage, and needs an owner.
- Development database report: PASS, 36 checks, 1 warning (finding 6). See `docs/evidence/scrum-136/data_quality_report.md`.

## Remaining noncritical limitations

- **Minutes are whole numbers.** Stints under a minute round to 0 and can carry stats (finding 6).
- **2025-26 coverage is thin.** The development database has 43 rows for 2025-26, all for one player, and 5,004 for 2024-25. That's a data-loading gap, not an inconsistency. Run `incremental_refresh` or the backfill for current-season players before relying on 2025-26 features.
- **99 active players have no `team_id`.** These are roster gaps; team features resolve affiliation from game history instead.
- **The CI seed is tiny** (2 stat rows). The CI report step proves the checks run and the seed is valid, not that production-scale data is clean. Run the report against the development database before feature freeze.
- **`predictionsApi.test.js` fails** as described above; it's outside Data & Storage scope.
