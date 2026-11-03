# SEC-04 manual assessment worksheet

**Status: NOT EXECUTED — template for completing missing manual evidence.**
An empty field or example below is not a pass or reviewer sign-off. Use with the
[interim assessment](sprint4_cc7_2_compliance_assessment.md) and
[accepted proposal](https://docs.google.com/document/d/1l8euXlMGXi-CjAZtP_0K2UOqW0aluzsx/edit).
Complete a copy for each review and retain its dated version.

## Assessment record

| Field | Value to complete |
| --- | --- |
| Test / proposal scenario | M01 / S4-C06, M02 / S4-C09, M03 / S4-C07, or M04 / S4-C08 |
| Date/time and time zone | PENDING |
| Executor | PENDING |
| Reviewer / escalation contact | PENDING — must be confirmed by the team |
| Environment and scope | PENDING — use an approved disposable database/snapshot |
| Commit / PR / Jira | PENDING — exact URLs and tested revision |
| Expected result | PENDING |
| Actual result / PASS, FAIL, BLOCKED | PENDING |
| Evidence paths/URLs and full SHA-256 | PENDING |

Do not include a database URL, `.env`, tokens, passwords, raw request headers or
unsanitized error messages. A report timestamp, game date, and successful refresh
timestamp are different facts; record the actual type of each date.

## M01 — Manual anomaly analysis and escalation (S4-C06)

1. Select an actual captured event from
   [failure-test evidence](evidence/ingestion-failure-tests.xml), and a detected
   anomaly from a controlled database test/query. Identify the test case, fixture
   and report; identify it as synthetic rather than a production incident.
2. Read the event's safe category, stage/row or player/season, and affected counts.
   For the database anomaly, record the named query and offending record keys.
   Confirm whether any successful writes remain and compare retained snapshots.
3. Classify each event as expected synthetic failure, routine operational failure,
   data defect, or possible security event. Record why the evidence supports that
   classification, what else was checked, and what remains unknown. A duplicate
   or timeout alone does not establish malicious activity.
4. Record response: explain/retry/fix/escalate, along with the owner and Jira link.
   Do not delete history to suppress the anomaly. Review unexpected identity
   changes, unexplained corrections and suspected unauthorized access with the
   designated reviewer; coordinate API concerns with Brandon's SEC-03 scope.
5. Repeat the relevant checks after remediation and record the result. Obtain a
   named human review and disposition. If the reviewer has not been agreed or no
   review occurred, mark BLOCKED instead of closing the scenario.

| Actual evidence/test case | Observed event and scope | Classification and rationale | Response / escalation / Jira | Retest and reviewer sign-off |
| --- | --- | --- | --- | --- |
| PENDING | PENDING | PENDING | PENDING | PENDING |

Example event shape only: `row_failed stage=player_game_stats row=1 error_type=IntegrityError`.
Record the exact observed event and its provenance; do not copy this example as
proof of an executed review.

## M02 — Stored/source comparison (S4-C09)

1. Choose a small, explained sample of actual stored eligible player-game rows.
   Include at least one refreshed record and one preserved historical record;
   document the sample selection. The proposal sets no numerical sample minimum,
   so record the size agreed with the reviewer rather than inventing approval.
2. Retain a read-only SQL result/export of the stored fields. Map internal player,
   team and legacy game IDs to the source identities explicitly. A source research
   CSV is not a substitute for a stored-database result.
3. Use a retained trusted source record, such as the
   [ESPN response excerpts](samples/espn_feature_responses.json), after confirming
   it refers to the same appearance. Compare points, minutes, shooting counts,
   opponent and home/away fields as appropriate. This is a data comparison, not
   endpoint/network/API-contract verification.
4. Document transformations: percentages 0–100 versus 0–1, minute rounding,
   Eastern-calendar dates and reconciled identities. Record any discrepancy,
   expected transformation or unresolved defect; do not silently adjust values.
5. Attach source capture date/hash, stored export/hash, query, environment,
   observed result, discrepancy disposition and human sign-off.

| Player/game and identity mapping | Source reference/capture date | Field | Actual stored value | Source value / normalization | PASS/FAIL/BLOCKED and explanation | Reviewer/date |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## M03 — CI gate and retained reports (S4-C07)

1. Open the [verified main CI run](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41556385360).
   Record the run/commit, named data steps and their actual outcomes. Do not rely
   on an empty summary table or the workflow's overall green badge alone.
2. Using authorized GitHub access, download `test-results-140`. Enumerate files;
   verify that failure, anomaly and refresh JUnit reports exist and parse. Record
   full report hashes and counts. Current artifact contents have not been checked.
3. If reports are missing, retain that finding. Coordinate with Jacob to separate
   report directories from Playwright's cleaned output and rerun verification.
4. In a disposable branch, coordinate one intentional failed **data** assertion.
   Confirm that the required job fails and its report survives; confirm the
   configured required-check names and branch-protection behavior with the owner.
5. Remove the deliberate failure before proposing a merge. Record the negative
   run and the restored passing run separately; never submit a deliberately
   broken main branch as evidence collection.

| CI run / commit | Named step and outcome | Required-check verification | Artifact files / hashes | Reviewer / result |
| --- | --- | --- | --- | --- |
| PENDING | PENDING | PENDING | PENDING | PENDING |

## M04 — Two-run reproducibility evidence (S4-C08)

1. Select an unchanged clean input snapshot; record its full SHA-256, source and
   the generation code revision. Keep the source and code fixed between runs.
2. Run the existing dataset generation procedure twice in the same controlled
   environment. Use [dataset versioning guidance](modeling_dataset_versioning.md).
   Retain two separately named output metadata manifests and output references;
   do not overwrite the first manifest with the second.
3. Compare full output dataset SHA-256 values and schema/row counts. Generation
   timestamps may differ and are not proof of a refresh. If hashes differ,
   investigate input, code, ordering and environment before marking PASS.
4. Record actual results and reviewer. A unit-test equality assertion supports
   implementation behavior but is not both retained generation manifests.

| Generation | Input hash | Code revision | Dataset hash | Schema / rows | Manifest and output reference | Time / result |
| --- | --- | --- | --- | --- | --- | --- |
| Run 1 — PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Run 2 — PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

Final comparison, discrepancy disposition, reviewer and date: **PENDING**.
