# NBA Ingestion Retry and Failure Recovery (SCRUM-138)

## Failure points reviewed

| Failure point | Before | Now |
|---|---|---|
| ESPN HTTP request (`request_json`, used by every ESPN fetch) | One try; a single timeout, reset or 5xx failed the whole player-season | Bounded retry with exponential backoff for recoverable errors |
| Incremental refresh (`incremental_refresh.refresh_player`) | Already one transaction, journaled, skips existing rows | Unchanged; benefits from request retries |
| Historical backfill (`historical_backfill`) | Row-by-row autocommit: a failed row left a partial season (games without stats) | Each player-season is one transaction; any failed row rolls the season back |
| Malformed source data (bad stats, wrong event, error payload) | Raises `ValueError` | Unchanged, and **not retried**: retrying can't fix bad data |

## Retry policy

Defined in `data/collection/espn.py`.

| Setting | Value |
|---|---|
| `RETRY_ATTEMPTS` | 3 tries in total, so at most 2 retries. The loop is bounded and can't run forever. |
| `RETRY_BASE_DELAY` | 1 s, doubling each time: wait 1 s, then 2 s |
| Retried | `ConnectionError`, `Timeout`, `ChunkedEncodingError`, invalid/truncated JSON, HTTP 429/500/502/503/504 |
| Not retried | Other HTTP 4xx (e.g. 404), ESPN `error` payloads, non-object payloads, and validation errors in parsing |

Worst case for one request: 3 × 15 s timeout + 3 s of waits ≈ 48 s. The web pages
(player search, upcoming games) use the same function, so during a full ESPN
outage they now take longer to report failure.

## Logging

All lines go to the `data.ingestion` logger. They contain only the request path,
attempt count, HTTP status and exception class. URLs, query strings and messages
are left out because they can carry sensitive details.

```
WARNING espn_request_retry path=athletes/3975/gamelog attempt=1 status=503 error_type=HTTPError delay_s=1.0
INFO    espn_request_recovered path=athletes/3975/gamelog attempts=2
ERROR   espn_request_failed path=athletes/3975/gamelog attempts=3 status=None error_type=Timeout
```

Failures are also recorded where they were before:
- Incremental refresh: a `failed` row in `ingestion_refresh_runs` with `error_type`
- Backfill: `player_season_failed`, and `backfill_incomplete` with exit status 1

## Preserving existing records

- All ESPN data for a player-season is fetched before any database write. A
  retrieval failure therefore writes nothing.
- **Incremental refresh:** one transaction per player-season; existing rows are
  skipped, never updated. A failure rolls back, and `last_successful_refresh`
  doesn't move (see `docs/data_freshness_tracking.md`).
- **Backfill:** `ingest_player_season` wraps games and stats in one transaction.
  If any row fails, the whole season rolls back with `ValueError`. Earlier seasons
  and other players stay as they were, and the backfill moves on to the next player.

## No duplicates on retry

- Retries happen per HTTP request, before any write, so nothing is ever written twice.
- Rerunning a refresh skips stored `(player_id, game_id)` keys.
- Rerunning a backfill upserts on the `(player_id, game_id)` primary key.
- Game IDs are reconciled by date and teams (`canonical_game_id`).

## Tests

- `tests/test_espn.py`: retry then recover, with 1 s/2 s backoff and logs; stops after 3 attempts for timeouts, connection errors, 500 and 429; 4xx not retried; truncated JSON retried; error payloads not retried.
- `tests/test_ingestion_retry_recovery.py` (real PostgreSQL temp tables, offline ESPN fixtures served through a fake `requests.get`):
  - a flaky source recovers and the refresh completes as `fresh`
  - a dead source stops at the retry limit, keeps existing history and records a `failed` attempt
  - rerunning after recovery adds no duplicates
  - a backfill season with a malformed row rolls back completely, then succeeds and reruns without duplicates
- `tests/test_ingestion_failure_logging.py`: existing safe-logging tests, updated for the transactional backfill.

`tests/conftest.py` sets `RETRY_BASE_DELAY = 0` for every test, so retries don't slow the suite.

## Limitations

- `Retry-After` headers are ignored; the fixed backoff is used.
- There's no jitter and no circuit breaker. Each request retries on its own, so a
  long outage costs about 48 s per request rather than failing fast.
- Database errors aren't retried. A failed write rolls back, and the run can simply be repeated.
