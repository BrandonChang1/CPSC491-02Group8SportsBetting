# Incremental NBA refresh and persistent freshness tracking

The incremental refresh command handles one internal player ID and NBA season.
It records attempts in PostgreSQL, appends missing player-game records, and leaves
existing raw game statistics unchanged. It reuses the ESPN adapter, game-ID
reconciliation, ingestion functions and credential-safe command runner.

## Setup and commands

Configure `DATABASE_URL` privately, install the project's existing dependencies,
and apply migrations:

```sh
npm run migrate
python -m data.ingestion.incremental_refresh --player-id 201939 --season 2026-27
python -m data.ingestion.incremental_refresh --player-id 201939 --season 2026-27 --status
```

Teams and the selected player must already exist through the existing roster
ingestion/setup. IDs are internal NBA IDs, not raw ESPN IDs. Season format is
`YYYY-YY`; the adapter translates it to ESPN's ending year. Use the intended
season explicitly; the command does not infer which dataset should be current.

Refresh exits 0 for a committed success (including a nonempty source with no new
records), and 1 for a detected failure. Invalid arguments produce usage errors.
The existing demo ingestion and historical backfill retain their behavior; they
do **not** populate this new journal. Use the incremental command when persistent
attempt tracking is required. No scheduler is installed.

`--status` does not fetch ESPN or write data. It prints the latest attempt and
last successful refresh for the exact player/season, plus `is_stale`. No attempts
prints JSON `null` and exits 1. It exits 0 only when the latest attempt succeeded
and the last successful refresh is at most **48 elapsed hours** old. A failed,
running, never-refreshed or stale scope returns 1. This is a proposed refresh-age
policy to confirm with the owner, not a provider SLA.

Applications can call
`data.ingestion.incremental_refresh.get_refresh_status(player_id, season)` or
query `ingestion_refresh_runs`. The Python result is a dictionary containing
timezone-aware datetime values; the CLI serializes them as timestamp strings
with offsets. Failure of the latest attempt and age of the previous success are
separate facts: a recent success can coexist with a later failed attempt.

## Stored records and transaction behavior

Migration [`005_ingestion_refresh_runs.sql`](../database/migrations/005_ingestion_refresh_runs.sql)
adds a table and scope index; [`schema.sql`](../database/schema.sql) includes the
same definition for fresh/disposable setups. No historical records are deleted
or rewritten by the migration.

| Field | Meaning |
| --- | --- |
| `id`, `player_id`, `season`, `source` | Durable attempt identity, exact scope, and source `ESPN`. No player foreign key is imposed on the journal so an invalid/unknown player's failure can still be retained. |
| `started_at`, `finished_at` | Database-clock `TIMESTAMPTZ` values representing UTC instants; display offset follows the database session. A running attempt has no finish time. |
| `status` | `running`, `succeeded`, or `failed`. |
| `source_rows` | Number of cleaned rows returned by the source, including existing rows. It is 0 if retrieval failed before returning data. |
| `inserted_rows` | Committed new player-game rows; 0 for failures because the batch rolls back. |
| `skipped_rows` | Existing canonical player-game identities encountered and skipped. On a failed validation pass, this may be only the rows classified before the error. |
| `error_type` | Exception class only, not a raw message, URL, credential or traceback. |

`last_successful_refresh` is derived as the maximum `finished_at` of succeeded
attempts for the scope. It is not a mutable pointer that a failed attempt could
advance. `is_stale` is true when no success exists or it is older than 48 hours.

1. Commit a `running` journal entry before requesting source data.
2. Fetch the selected season using the existing ESPN game-log/box-score adapter.
   A missing/empty result is conservatively treated as failure; it cannot advance
   last-success metadata. It may require operator review for a player with no
   appearances in that season.
3. Begin a transaction and acquire a player-scoped PostgreSQL advisory lock.
   Refreshes through this command serialize per player, even across seasons.
4. Reconcile every source game against stored game date/home/away identities.
   Reject ambiguous/changed identities, duplicate canonical or natural identities,
   and wrong player scope. Skip existing player-game keys; do not rely only on a
   maximum game-date watermark, which could hide older gaps.
5. Validate new required points/minutes/rebounds/assists as finite, nonnegative
   values and reject future dates. The existing adapter and database constraints
   retain their additional validation. Insert new games/stats through the shared
   ingestion functions using the same connection.
6. Recalculate this player's rolling minutes from the **full stored history**,
   then update the attempt to succeeded inside the same transaction. No-op
   successes still record that a nonempty source was checked.
7. On a supported error, roll back the complete batch and persist a failed
   outcome outside that transaction. The previous successful time remains intact.

The shared helpers accept an optional connection so their writes and context
updates participate in this transaction. Existing callers can omit it. Existing
raw statistics are skipped even if the new source reports a correction; deliberate
historical correction remains a separate reviewed ingestion operation. Derived
`recent_minutes_avg` values can change when an older missing appearance is added;
the new history must be included to keep future features correct.

If the process stops during a write, PostgreSQL rolls back the transaction and
the earlier journal entry remains visibly `running`. It is an incomplete/unknown
attempt, not proof of an active worker. The status command returns 1; review it
and rerun safely. No background process automatically marks abandoned runs failed.
If the database is unavailable before the attempt can be created, a database
record is impossible; the existing safe stderr diagnostic and nonzero command
status are the available signal. A connection loss while finalizing can likewise
leave an incomplete attempt requiring review.

## Freshness and scope limits

The earlier [expected-game monitor](refresh_freshness_monitoring.md) asks whether
a known appearance is stored after a two-Eastern-calendar-day grace period. This
new status query asks whether this scope was successfully refreshed within 48
elapsed hours. These are different clocks and checks; use both where needed.
A recent success is not proof that ESPN supplied every expected game, that the
entire NBA dataset is current, or that historical raw corrections were applied.

The source API still returns a season log and the adapter can retrieve existing
box scores; incremental behavior is at the storage boundary, not an API delta
feed. Large histories may be slower. This task adds no live source completeness
audit, all-player scheduler, alert delivery, automatic roster ingestion, retry
service, volume threshold or new HTTP endpoint. Database access must be limited
to approved operators/services; a read-only consumer needs SELECT only on the
journal, while refresh execution needs its data-write permissions.

For failures, query the attempt ID, counts, safe error category and prior success;
compare the expected-game check and follow the
[anomaly review/recovery procedure](ingestion_failure_review.md). Never delete
history to clear a freshness alert. Journal retention and reviewer escalation
still require an agreed operational policy.

## Acceptance criteria and evidence

| Requirement | Verified behavior |
| --- | --- |
| Newly available records can be ingested | First and later appearances are inserted; an older missing appearance is also recovered. |
| Existing valid history remains preserved | Raw existing/legacy records are skipped. Invalid scope/identity, rejected data, SQL/post-processing errors and interruption leave historical rows intact. |
| Repeated ingestion introduces no duplicates | Repeated runs add no rows; legacy game IDs are reused; conflicting source identities are rejected. |
| Last success and outcome are recorded | Started/finished timestamps, source, row counts, success/failure and scope are retained; no-op checks are successes; failed runs do not advance the last-success time. |
| Failed attempts support CC7.2 monitoring | Safe failed-attempt records, visible incomplete runs, read-only status with nonzero monitoring status, and documented recovery. |

Tests in [`test_refresh_tracking.py`](../tests/test_refresh_tracking.py) use real
PostgreSQL transactions, temporary schema copies and offline ESPN fixtures. They
include API failure, SQL failure after an earlier row write, post-processing
failure, interruption after stat writes, retry, cold-start/stale status, source
validation, legacy identity and full-history rolling context. Logs/journal fields
are checked for synthetic credential leakage. No live ESPN calls are made.

Run the grouped tests against a disposable migrated database:

```sh
python -m pytest tests/test_refresh_tracking.py tests/test_incremental_refresh.py \
  tests/test_data_freshness.py -v --junitxml=assessment-results/incremental-refresh.xml \
  -o junit_logging=all
```

CI runs this group after Playwright and uploads only its XML under
`assessment-results/`, separately from Playwright's cleaned `test-results/`.
Existing historical reports are not overwritten by this task's capture.
The actual CI run/artifact link must be added after the PR executes.

### Local execution record

- Base revision: `e4369bb`, plus this task's working-tree changes.
- Environment: local Python 3.11 and disposable PostgreSQL 18; no production
  queries or live ESPN calls. The new migration applied through `npm run migrate`
  and was safely skipped when the migration runner was repeated.
- Refresh/freshness group: **45 passed** (24 new tracking cases, 6 existing
  incremental preservation cases, 15 existing freshness cases), zero failures,
  errors or skips; [JUnit evidence](evidence/incremental-refresh-tracking.xml).
- Full Python regression: **275 passed**, zero failures, errors or skips;
  [JUnit evidence](evidence/incremental-refresh-regression.xml). This count
  includes the grouped tests; the report totals should not be added together.
- Repository Python lint, CLI help and diff checks passed. Existing scikit-learn
  artifact/runtime version warnings remain; no model/dependency changes were made.
- GitHub CI, live refresh throughput, concurrent-worker stress testing, deployed
  scheduling and alert delivery were not exercised. The SQL advisory lock is
  implemented; the tests establish sequential retry behavior and atomic rollback.

| Report | SHA-256 at capture time |
| --- | --- |

| `incremental-refresh-tracking.xml` | `dd6c0c1fc7a204b73ee1f22f129579115f7c5a4250f384b443b93e9f5e33d1d2` |
| `incremental-refresh-regression.xml` | `911616798e8da0bfb0e7136ac475ebb3ab33efe488e066d5995341897df1c8ba` |
