# Ingestion failure logging and anomaly review

This procedure covers the ESPN NBA ingestion commands, including the historical
backfill. ESPN is the current NBA data provider; the Jira task's “NBA API” failure
cases are simulated at the ESPN request boundary. No live outage or production
database modification is needed to run the failure tests.

## Available signals

Both supported commands configure Python stderr logging with local timestamps
(without time-zone offsets), severity, and a diagnostic message:

```sh
python -m data.ingestion.database_ingestion
python -m data.ingestion.historical_backfill
```

| Signal | Meaning / action |
| --- | --- |
| `row_failed stage=... row=... error_type=...` (ERROR) | A team, player, game or stat row failed. The row is a 1-based iteration position within that stage; correlate it with the retained input batch in restricted storage. Later rows are still attempted. |
| `player_season_failed player_id=... season=... error_type=...` (ERROR) | Backfill could not fetch or ingest a player's season. Later players/seasons are still attempted. |
| `no_game_logs player_id=... season=...` (WARNING) | Backfill received empty history. This may be valid for that player/season, but requires checking coverage. It is not automatically counted as an exception. |
| `ingestion_incomplete stage=game_logs reason=empty_response` (ERROR) | The single-player ingestion command had no game logs and stopped before inserting games/stats. |
| `ingestion_incomplete failed_rows=...` (ERROR) | One or more stages reported failed rows. A completion message is not printed. |
| `backfill_incomplete failures=... target_reached=...` (ERROR) | Backfill had row/player failures or did not reach its configured row target. Counts include failed game rows as well as stat rows. |
| `ingestion_failed command=... error_type=...` (ERROR) | A supported API, validation/configuration, or database exception escaped a stage. The command stopped with safe diagnostics. |
| stdout stage totals | Existing `processed`, `successful`, and `failed` summaries. A player can fail more than one stage; the failure total counts events/rows, not distinct players. |

Exit status **0** means the command completed with no counted failures (and, for
backfill, reached the target). Status **1** means a supported fatal exception or
an incomplete run. A zero status is not proof of source completeness or data
correctness; run the stored-data anomaly checks as well.

Logs deliberately omit raw exception messages, traceback objects, database URLs,
request URLs/headers, response bodies, and failed row contents. Error type plus
stage/row or player/season identifies the failure without copying potentially
sensitive exception text. Examples use standard exception classes such as
`Timeout`, `HTTPError`, `OperationalError`, `IntegrityError`, and `KeyError`.
There is no regex-based redaction that could miss an unfamiliar credential format.

These are command-level protections. Direct Python callers of ingestion helpers
still receive fatal exceptions and must avoid logging raw exceptions themselves.
Unexpected programming errors outside the command runner's supported exception
classes can still produce a traceback; review access before distributing logs.
No remote log service, alerting rule, or log-retention policy was added.

## Review procedure

1. Record the command, start time/time zone, revision, requested player/season,
   intended environment, and exit status. Do not record the connection string,
   `.env`, passwords, tokens, request headers, or customer data. Capture stdout
   and stderr together in an access-controlled location. For example:

   ```sh
   python -m data.ingestion.historical_backfill > ingestion-review.log 2>&1
   ingestion_status=$?
   echo "ingestion_exit_status=$ingestion_status"
   ```

   The echo prints its own status afterward; use the saved `ingestion_status`
   for automation. Configure a scheduler to treat a nonzero command status as
   failure. The repository does not provision such a scheduler or alert.

2. Locate ERROR/WARNING events and compare the stdout stage counts. For API
   timeouts/HTTP errors, check provider availability and retry only the affected
   player/season after recovery. For `OperationalError`, verify database
   availability and access privately. For `IntegrityError` or validation errors,
   inspect the identified input row and database relationships in a restricted
   session. Do not paste raw database errors or credentials into Jira.

3. Check whether writes already succeeded. Ingestion uses autocommit, so a failed
   run can leave valid partial results. Existing upserts support reprocessing;
   do not delete historical data or reset tables as an initial recovery step.
   A post-processing error can occur after stat rows were stored. Re-run the
   failed scope and the rolling-minutes/team-context refresh as appropriate.

4. Run the anomaly suite against the intended populated review/test database
   using its configured `DATABASE_URL`:

   ```sh
   python -m pytest tests/test_pipeline_anomalies.py -v \
     --junitxml=test-results/anomaly-review.xml
   ```

   It checks duplicates, missing required values, non-finite/negative values,
   percentage ranges, inconsistent counting totals, and game/opponent context.
   Audit queries use read-only transactions. Detector self-tests use temporary
   tables rolled back on completion; the role requires SELECT and TEMP privileges.
   An empty database fails the audit. Record offending player/game identities and
   the named check; investigate before applying any correction. See also
   [data test setup](sprint3_data_testing.md).

5. After remediation, repeat the affected ingestion and anomaly checks. Record
   before/after counts, exit status, test results, and a short explanation. Close
   the review only when unexpected errors are resolved, expected empty histories
   are explained, and the relevant checks pass. A row-count target alone does not
   establish league-wide completeness.

6. Attach sanitized results and report hashes to the task. Keep operational logs
   in approved restricted storage; share only the minimum diagnostic excerpt.
   If any credential exposure is discovered, restrict access and follow the
   team's credential-rotation procedure before distributing evidence.

## Repeatable failure tests and acceptance evidence

From the project root, with the project's Python dependencies installed:

```sh
python -m pytest tests/test_ingestion_failure_logging.py -v \
  --junitxml=test-results/ingestion-failures.xml -o junit_logging=all
```

The 32 tests mock only requests and database/stage boundaries; they execute the
real ingestion loops, command result handling, and safe diagnostic calls. Existing
ESPN fixtures provide valid cleaned game logs. No network or PostgreSQL is
required for this suite. A simulated error is expected test input: a passing test
means the failure was detected and safely reported, not that the ingestion
attempt succeeded.

| Acceptance criterion | Evidence |
| --- | --- |
| Simulated API or ingestion failure is detectable | Timeout/HTTP error at the real request helper; database connection failures; 12 row-failure cases across four ingestion loops; partial-stage nonzero results; empty histories; post-processing errors. |
| Failures recorded without exposing credentials | Synthetic credential-bearing exceptions; assertions check captured stdout/stderr/logs for username, host, password and token sentinels; logged records must have no exception traceback attached. |
| Anomaly review documented | The review and recovery sequence above, with the existing stored-data audit. |
| Test results captured | [Local JUnit report](evidence/ingestion-failure-tests.xml), [anomaly regression report](evidence/ingestion-anomaly-review.xml), and the execution record below. CI runs the failure suite before Node setup and writes `test-results/ingestion-failures.xml`. The existing always-run artifact upload retains it with other reports for 30 days. |

Passing-test logs are included in JUnit through `junit_logging=all`, so reviewers
can see the safe diagnostic events emitted during the simulations. Do not enable
traceback/local-variable dumping when collecting operational evidence. Retain
longer-lived evidence in the team's approved location before CI artifacts expire.

### Execution record

- Date: November 2, 2026 (Pacific).
- Local focused run: 60 passed (32 failure simulations plus 28 existing parsing,
  ESPN response and game-log checks); see `ingestion-failure-tests.xml`.
- Local database regression run: 54 passed (35 anomaly checks, 6 ingestion
  idempotency/roster checks, and 13 database integrity checks), with zero failures,
  errors or skips. A disposable local PostgreSQL 18 database was loaded from
  `database/schema.sql` and `tests/fixtures/seed_ci_database.sql`; production data
  was not queried. CI independently uses PostgreSQL 16 and applies migrations.
- Repository base revision: `218d15d5aee8dd19795798c1f82211705fe0c036`, plus
  this task's working-tree changes. CI reports will bind results to the eventual
  committed revision.
- Scope: current ESPN adapter and the two ingestion commands. Live provider
  outages, deployment log collection/alerts, and credential rotation were not
  exercised.

Database regression command (with `DATABASE_URL` set privately to the disposable
database):

```sh
python -m pytest tests/test_pipeline_anomalies.py \
  tests/test_ingestion_idempotency.py tests/test_database_integrity.py -q \
  --junitxml=docs/evidence/ingestion-anomaly-review.xml
```

The focused local report also included `tests/test_database_ingestion.py`,
`tests/test_espn.py`, and `tests/test_nba_game_logs.py` alongside the failure suite.
Report SHA-256 hashes at capture time (rerunning pytest replaces the files):

| Report | SHA-256 |
| --- | --- |
| `ingestion-failure-tests.xml` | `f6e4d7c8c55c7a8ccc4874fb9dab00322ca0ff343c784b3ba9820377c7c7aa91` |
| `ingestion-anomaly-review.xml` | `01bfd103f9928abfe77de5f743c9ef70e2a580c34c2c47e8976c7bb70b9ed045` |
