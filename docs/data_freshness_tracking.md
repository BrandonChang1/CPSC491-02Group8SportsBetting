# NBA Data Freshness Tracking and Stale-Data Detection (SCRUM-137)

## Review of how successful updates were tracked

| Ingestion path | Records attempts? | Notes |
|---|---|---|
| `data.ingestion.incremental_refresh` (per player/season) | Yes, in `ingestion_refresh_runs` | Commits a `running` row first, then marks it `succeeded` inside the data transaction or `failed` after rollback. |
| `data.ingestion.historical_backfill` | No | One-time bulk load toward a row target; prints counts only. |
| `data.ingestion.database_ingestion` `main()` | No | Demo/setup load; prints counts only. |
| `scripts/check_data_freshness.py` | n/a (read-only) | Checks one *expected game date* is stored, with a 2-day grace period. Different question from refresh age. |

Before this task, `--status` reported one player/season's latest attempt and
`is_stale` with a hardcoded 48 hours. There was no database-wide view, no single
state value, and no backend access.

## The last successful refresh timestamp

`last_successful_refresh = MAX(finished_at) WHERE status = 'succeeded'` over the
scope's attempts in `ingestion_refresh_runs`. It is derived, not stored in a
separate field that could be overwritten, so a failed or interrupted attempt can't advance it:
- A failed attempt's batch rolls back and its row is marked `failed`.
- An interrupted attempt stays `running`.

Neither status is counted.

## Freshness states

| `freshness` | Meaning | Status command exit |
|---|---|---|
| `fresh` | Latest attempt succeeded, and the last success is within the threshold | 0 |
| `stale` | Latest attempt succeeded, but the last success is older than the threshold | 1 |
| `failed` | The latest attempt failed (`error_type` holds the exception class only) | 1 |
| `running` | The latest attempt is in progress or was interrupted | 1 |
| `never_refreshed` | No successful attempt recorded for the scope | 1 |

The latest attempt's outcome takes precedence over age. A failed attempt after a
recent success is `failed`, and `last_successful_refresh` still shows the earlier
success. `is_stale` is reported separately: it is true when there is no success,
or when the last success is older than the threshold.

Scopes:
- **Database**: every player and season. Answers "has the database received a successful update recently?"
- **Player/season**: one exact `player_id` + `season`.

## Configurable threshold

Default **48 hours**. The first of these that is set wins:

1. `--max-age-hours` (CLI) or the `max_age` argument (Python)
2. the `DATA_FRESHNESS_MAX_AGE_HOURS` environment variable (also read by the backend)
3. 48

Values must be positive, finite numbers; anything else is rejected.

## Accessing freshness

Command line (read-only, no ESPN calls):

```sh
python -m data.ingestion.incremental_refresh --status                                   # whole database
python -m data.ingestion.incremental_refresh --status --player-id 201939 --season 2025-26
python -m data.ingestion.incremental_refresh --status --max-age-hours 24
```

Python:

```python
from data.ingestion.incremental_refresh import get_database_freshness, get_refresh_status
get_database_freshness()                  # always a dict
get_refresh_status(201939, "2025-26")     # None if the scope was never attempted
```

Backend (Node, read-only, no prediction-model changes):

```
GET /health/freshness
GET /health/freshness?player_id=201939&season=2025-26
```

```json
{
  "scope": "database",
  "freshness": "failed",
  "is_stale": false,
  "max_age_hours": 48,
  "last_successful_refresh": "2026-11-16T14:02:11.000Z",
  "latest_attempt": {"status": "failed", "started_at": "...", "finished_at": "...", "error_type": "ConnectionError"}
}
```

`player_id` and `season` must be given together (400 otherwise). The SQL is
duplicated in `backend/app/routes/health.js` and `FRESHNESS_QUERY` in
`data/ingestion/incremental_refresh.py`, so change both together.

## Tests

- `tests/test_refresh_tracking.py`: real PostgreSQL temp tables. Covers never_refreshed → fresh → stale → failed transitions; failed attempts not moving `last_successful_refresh`; the threshold through argument and environment; invalid thresholds; the database-wide CLI; and argument validation.
- `backend/tests/freshness.test.js`: the endpoint's fresh, stale, failed-after-success and never_refreshed states, the environment threshold, database scope, and 400s for a bad scope. It writes rows for throwaway player IDs and deletes them afterwards.

Both run in the existing CI steps ("Validate incremental refresh tracking" and "Run backend automated tests").

## Limitations

- The backfill and demo ingestion don't record attempts. Database freshness reflects only `incremental_refresh` runs, so a database loaded only by backfill reports `never_refreshed`.
- Nothing marks an abandoned `running` row as failed. The next attempt supersedes it.
- No scheduler or alert delivery is included. Freshness is read on demand.
- A recent success means the source was checked, not that every expected game was stored. Use `scripts/check_data_freshness.py` for that.
