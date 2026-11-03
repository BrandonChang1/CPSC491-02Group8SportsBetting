# Data refresh and freshness anomaly monitoring

Follow-up implementation: [incremental refresh tracking](incremental_refresh_tracking.md)
now provides a separate command with persisted attempt outcomes and last-success
timestamps. The original assessment below records the earlier implementation;
its historical test results and stated gaps are retained as captured.

## Control and acceptance criteria

Incremental NBA ingestion should identify failed updates and overdue expected
data without losing valid historical records. The current provider is ESPN.
This assessment covers the repository commands and a disposable PostgreSQL
database, not a deployed scheduler or external alerting service.

| Acceptance criterion | Implementation / verification | Interim status |
| --- | --- | --- |
| Failed refresh attempts can be identified | Existing ingestion counters, safe ERROR logs, and nonzero exit statuses; new database tests simulate failed inserts and failed updates, detect missing stats, and verify recovery. | Verified locally |
| Abnormal freshness is flagged using a documented threshold | Read-only, player-scoped expected-game check; missing data becomes an ERROR after more than two Eastern-calendar days. Boundary, empty-history, and hidden-gap tests are included. | Verified locally |
| Previously valid history remains intact | Full stored-row snapshots compared before/after incremental inserts, retries, truncated inputs, rejected identity changes, and database-rejected updates. Temporary-table tests exercise the actual upsert functions. | Verified for these scenarios |
| Expected monitoring behavior is documented | Threshold, required scope, signals, exit statuses, execution steps, and limitations below. | Documented |

Overall: **verified for the tested local scenarios; operational monitoring is
partially verified** until deployment scheduling, alert delivery, and real
expected-game selection are exercised. GitHub CI execution must be linked after
the PR runs; local reports are not evidence of a completed CI run.

## What freshness means here

The schema has game dates but no persisted ingestion-attempt timestamp. Therefore,
this check establishes whether a particular player's **expected completed game**
has corresponding player-game stats. It does not measure the last successful
refresh time, detect a scheduler that never ran, or establish ESPN source latency.

The caller supplies an internal `player_id` and `expected_game_date`, based on a
known completed, eligible game in which that player appeared. Do not use today's
date by default, a future scheduled game, a DNP, or an off-day. This explicit
expectation avoids assuming every player plays every day, including in the
offseason. Schedule/box-score confirmation and automated expectation selection
are operational responsibilities outside this check.

The query uses `player_game_stats JOIN games`, restricted to the selected player.
A game shell without that player's stats does not count as a completed refresh.
The exact expected date is checked, so newer data for the same player—or fresh
data for a different player—cannot hide that missing appearance.

## Threshold and signals

`MAX_DELAY_DAYS = 2` in
[`scripts/check_data_freshness.py`](../scripts/check_data_freshness.py).
This is a proposed project monitoring policy, not a measured ESPN service
guarantee. It allows routine next-day ingestion plus a one-day recovery buffer.
Review the threshold when an actual refresh schedule and source-latency data
are available.

```text
delay_days = as_of_date - expected_game_date
overdue = expected player-game stats are missing AND delay_days > 2
```

Both dates are calendar dates interpreted for the NBA's America/New_York day.
The default as-of date is today's Eastern date; `--as-of-date` makes audits
reproducible. This is not a precise 48-hour timer because tipoff/completion times
are not stored. A January 10 appearance remains pending on January 12 and is
overdue on January 13 if its stats are still missing.

| Condition | Diagnostic | Exit status |
| --- | --- | ---: |
| Exactly one appearance on the expected date and no future-dated stats | INFO `freshness_ok` | 0 |
| Expected date missing, including empty history, within the two-day grace period | WARNING `refresh_pending` | 0 |
| Expected date missing after the grace period | ERROR `freshness_anomaly reason=missing_expected_game` | 1 |
| A stored player-game date is later than the as-of date | ERROR `freshness_anomaly reason=future_record` | 1 |
| More than one appearance on the expected date | ERROR `freshness_anomaly reason=multiple_appearances` | 1 |
| Invalid player ID, future expected date, or supported database/configuration error | ERROR `ingestion_failed` with error type only | 1 |
| Malformed/missing CLI arguments | argparse usage error | 2 |

Status 0 includes **pending**, so reviewers must read the diagnostic. It does
not always mean data has arrived. Missing data is never silently labeled fresh.
The monitor cannot establish whether all fields in a present row are correct;
use the existing anomaly and integrity suites for that assessment.

Logs contain the selected numeric player ID, expected/latest dates, delay and
threshold where applicable. The shared safe command runner omits raw database
exception messages and tracebacks. No connection URL, password, request headers,
or failed row payload is logged by the monitor.

## Execute and review

Set `DATABASE_URL` privately for the intended database. From the project root:

```sh
python -m scripts.check_data_freshness \
  --player-id 201939 --expected-game-date 2025-04-13 \
  --as-of-date 2025-04-16
```

The dates above illustrate a historical audit. Choose the actual expected game
and audit date for a live review. A modern database with later games would be
flagged for future records relative to that historical as-of date; use an
appropriate snapshot or a current as-of date instead.

1. Run the intended ingestion command, capture its exit status and sanitized
   stdout/stderr, and inspect stage totals. Any nonzero refresh result requires
   immediate review; the freshness grace period does not excuse a failed run.
2. Run the freshness command for each expected player/game scope, retaining its
   as-of date, status, and diagnostic. It uses a read-only transaction and
   requires SELECT permission on `games` and `player_game_stats`.
3. For pending data, retry after the next planned refresh. For overdue data,
   inspect provider availability, database access, mappings, and ingestion errors.
   Confirm the expected date and player participation before treating the gap
   as a pipeline failure.
4. Retry the affected scope after correction, then rerun freshness and stored-data
   anomaly checks. Do not delete historical records to clear an alert. See
   [ingestion failure review](ingestion_failure_review.md) for the recovery steps.
5. Attach sanitized results, the PR/CI link and Jira task link to the Sprint 4
   assessment. Record whether the finding was resolved or remains pending.

No automatic invocation was added to the demo ingestion command: that command
uses a fixed historical season and does not identify an expected current game.
An operational scheduler must invoke the monitor explicitly with confirmed
expectations and route nonzero results to an owner. No scheduler or alert
delivery is claimed by this implementation.

## Historical preservation and unexpected changes

The production upsert behavior is unchanged. New or truncated batches do not
delete history; retries reuse keys; conflicting game identities are rejected.
PostgreSQL statement atomicity preserves an existing row when its update fails
type/constraint validation. A failed batch can still leave successfully inserted
game shells or other valid partial writes because ingestion uses autocommit.
The monitor specifically checks for missing player stats in those cases.

Existing rows are not immutable: legitimate source corrections for the same
player/game can update stats. This task does not add a before/after audit ledger,
approval for corrections, or a prohibition on historical updates. Semantically
bad values that satisfy database types/constraints are not guaranteed to be
blocked; run the existing anomaly suite to detect inconsistent totals, negative
counts, non-finite values, and invalid game context. The preservation claim is
limited to the tested incremental and rejected-update scenarios.

## Tests and evidence

The 15 offline cases in
[`test_data_freshness.py`](../tests/test_data_freshness.py) cover on-time data,
grace-period boundaries, overdue/empty history, exact-date gaps behind newer
data, future records, multiple appearances, invalid scope, read-only command
setup, and credential-safe database failure reporting.

The six PostgreSQL tests in
[`test_incremental_refresh.py`](../tests/test_incremental_refresh.py) verify:

- Incremental insertion and an idempotent retry preserve full existing rows.
- A failed insert leaves history intact, is logged, and produces a freshness
  anomaly; a retry restores freshness.
- Changed game identity cannot overwrite historical stats or game context.
- A database-rejected update retains all previously valid stored values.
- Truncated refresh input does not delete previously stored appearances.
- Newer data does not hide a missing date, and the monitor changes no stored rows.

These tests use connection-local temporary copies of the schema, including real
constraints and indexes. They disappear on connection close, including after a
failure. No synthetic records are inserted into permanent tables, and no live
ESPN requests are made. The test role needs TEMP privilege and schema-creation
capability in its disposable environment. Existing failure simulations additionally
cover API timeouts/HTTP errors, partial counters, and command exit statuses.

Repeat the dedicated suite against a disposable PostgreSQL database:

```sh
python -m pytest tests/test_data_freshness.py tests/test_incremental_refresh.py -v \
  --junitxml=test-results/refresh-freshness.xml -o junit_logging=all
```

CI runs this command after schema migrations and deterministic seeding. The
existing always-run artifact upload retains `test-results/refresh-freshness.xml`
with the other reports for 30 days. Retain the relevant CI run/PR links in the
Google Doc before those artifacts expire.

### Local execution record

- Environment: local Python 3.11, disposable PostgreSQL 18 with the project schema
  and deterministic seed. CI uses Python 3.12 and PostgreSQL 16; it has not been
  executed as part of this local verification.
- Base revision: `4c176699e1e76cd1a3b4c02171369ddcf045351b`, plus task changes.
- Dedicated tests: **21 passed**, zero failures, errors or skips; see
  [JUnit evidence](evidence/refresh-freshness.xml), including passing-test logs.
- Full Python regression: **251 passed**, zero failures, errors or skips; see
  [full regression evidence](evidence/refresh-full-regression.xml).
- Repository Python lint and `git diff --check` passed.
- Full-suite verification exposed a stale duplicate loader/path/model label in
  `ml/predict_player.py`. Removing that block restored the existing manifest-
  verified model loader; the outdated prediction test version assertion was
  aligned with the approved linear-regression model. Model integrity/version
  tests pass, and no integrity validation was weakened.

Report SHA-256 values at capture time (rerunning tests replaces the reports):

| Report | SHA-256 |
| --- | --- |
| `refresh-freshness.xml` | `2c732679ff6b3eb3cc8de82c77bc4811c3281be2a81c97a4a36d67bc34b6b858` |
| `refresh-full-regression.xml` | `7aa62b3db55426cc1b594940e64bf03fb63e9dbc841a2449b3eb12ea264e8802` |

Remaining operational work: confirm the two-day policy with the refresh owner,
automate expected-game selection, schedule checks and verify alert delivery.
If measuring actual refresh execution age is required, add persisted run
timestamps/statuses and assess those separately. Local evidence does not prove
these deployment behaviors.

### Verification after merging main

The merge with `origin/main` at `b03bc82` retains main's approved random-forest
artifact, manifest verification, feature schema and model label. The overlapping
model-label conflict was resolved and the prediction test expectation was updated
to `random-forest-points-v1`. Freshness-monitoring changes were retained.
The refreshed full-regression report records 251 passing tests. Local loading of
the approved random-forest artifact emits scikit-learn version warnings (artifact
1.8.0 versus installed 1.9.1); no model retraining or dependency change was made.
