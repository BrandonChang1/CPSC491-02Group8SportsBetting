# Sprint 4 Interim SOC 2 CC7.2 Compliance Assessment

**Assessor / control owner:** Caden Santiago, Data & Storage.
**Assigned control:** SEC-04 — Data pipeline integrity and failure monitoring.
**Assessment date:** November 2, 2026 (Pacific; corresponding GitHub events may be dated November 3 UTC).
**Evidence baseline:** repository commit `870f02cedac548d809b680b9f1ebeceed1161abb` plus this documentation package.
**Overall result:** **PARTIALLY VERIFIED / PARTIAL**. Local detection and recovery
tests have passing evidence; the full proposed operational control is not yet
demonstrated. This is an individual interim assessment, not a certification.

## 1. Proposal, criterion and assessment boundary

The source of the assignment, control statement and nine scenario IDs is the
[original Sprint 4 proposal, revised November 2](https://docs.google.com/document/d/1l8euXlMGXi-CjAZtP_0K2UOqW0aluzsx/edit).
Its text export was inspected for this assessment; the export hash and capture
time are recorded in the [evidence manifest](evidence/cc7-2/evidence_manifest.json).
This Markdown document supplements that proposal and can be pasted into its
Google Doc as the interim assessment. The linked Google Doc was not edited.

CC7.2 addresses monitoring system operations for anomalies and analyzing them to
determine whether they are security events. The reference framework is AICPA's
[2017 Trust Services Criteria with revised points of focus](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022);
the project applies a narrower ingestion-focused control, rather than claiming
to assess every system component. Criterion text is also available in AICPA's
[TSP Section 100 publication](https://us.aicpa.org/content/dam/aicpa/interestareas/frc/assuranceadvisoryservices/downloadabledocuments/trust-services-criteria-redlined.pdf).

The accepted project proposal requires each ingestion run to record its outcome,
counts, source, timestamps and errors; data checks to identify relationships,
duplicates, inconsistencies and stale loads; anomaly review and escalation; and
preservation of valid history during failures. Full proposed run records and
last-success metadata have not been implemented merely because tests pass.

| Responsibility | Assessment boundary |
| --- | --- |
| Caden, SEC-04 | Normalized/stored data, relationships, duplicates, ingestion failures, safe retries, freshness, dataset reproducibility and data-anomaly review. |
| Brandon, SEC-03 | ESPN endpoint identity, network/API security, API contracts, outage UI and betting/game-status restrictions. API failure is simulated only as an ingestion input here. |
| Swayam, SEC-05 | Model integrity, approved artifacts, serving versions and accuracy. Model tests in the full regression are context, not Caden's individual control evidence. |
| Jacob, SEC-01 | Required CI security gates and workflow enforcement. |
| Charlie, SEC-02 | Authentication, authorization and sessions. |

## 2. Personal Sprint 4 PR links

These five PRs were authored by GitHub account `cadensantiagoat` and cover the
work discussed for this sprint. All were merged when inspected. Confirm the
course's exact sprint date range before submission; this is not a claim that
all repository contributions belong to this individual.

| PR | Work | Relevance / Jira reference |
| --- | --- | --- |
| [#78 — ESPN migration](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/78) | Preserve legacy identities, source fixtures, ingestion and duplicate handling. | Supporting ingestion foundation; [SCRUM-108](https://csu-group-8.atlassian.net/browse/SCRUM-108). |
| [#80 — Automated data pipeline anomaly detection](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/80) | Duplicate, invalid-value and inconsistent-context detectors with SQL/pytest and CI. | Direct SEC-04 evidence; [SCRUM-102](https://csu-group-8.atlassian.net/browse/SCRUM-102). |
| [#81 — ESPN feature availability](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/81) | Nine-feature assessment, source examples, 575-row ML dataset and offline rebuild. | Related sprint work, not proof of deployed monitoring; [SCRUM-115](https://csu-group-8.atlassian.net/browse/SCRUM-115). |
| [#88 — Ingestion failure logging and anomaly review](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/88) | Safe diagnostics, incomplete-run exit statuses, failure simulations and review procedure. | Direct SEC-04 evidence; individual Jira issue URL still needed. |
| [#90 — Refresh freshness monitoring](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/90) | Expected-game freshness check, preservation/retry tests and retained reports. | Direct SEC-04 evidence; individual Jira issue URL still needed. |

The known Jira keys above are present in the PR titles/branches. Their issue
contents/status were not independently verified: anonymous access to the supplied
Jira site did not expose issue metadata. The
[Sprint board](https://csu-group-8.atlassian.net/jira/software/projects/SCRUM/boards/1)
is the supplied work-tracking entry point; it does not replace the missing
individual work-item links.

Also add the PR and Jira links for **this evidence-package task** after creating
the PR. No PR, issue, comment or commit was created by this assessment work.

## 3. Acceptance criteria and actual assessment results

Scenario IDs and pass criteria below are paraphrased from the original proposal.
**Verified / PASS** means the bounded scenario has supporting results.
**Partially verified / PARTIAL** means only part of its pass criterion is shown.
**Not yet tested / BLOCKED** means required execution/evidence is missing.
Missing evidence is not recorded as a test failure. The overall control remains
partial even where individual tests pass.

| Proposal ID | Acceptance criterion | Procedure and available result | Evidence | Status / remaining work |
| --- | --- | --- | --- | --- |
| S4-C01 | Reingest the normalized fixture twice without additional player/game records. | Idempotency and incremental retry tests compare counts and values and detect duplicate keys. Passing local results are retained. | E02, E03; `test_repeated_ingestion_is_idempotent`, `test_duplicate_player_game_records_remain_zero`, `test_incremental_insert_and_retry_preserve_history`. | **Verified / PASS** for controlled fixtures. |
| S4-C02 | Reject invalid writes or record invalid IDs, relationships, dates and inconsistent records. | Integrity/anomaly queries identify missing relationships and invalid stats; isolated bad-data tests prove detection. Identity conflicts and database-rejected updates preserve existing rows. However some type-valid semantic errors are detected after storage, not rejected at the write boundary. | E02, E03; [integrity tests](../tests/test_database_integrity.py), [anomaly queries and injected cases](../tests/test_pipeline_anomalies.py). | **Partially verified / PARTIAL**; expand normalized-record rejection coverage and document post-write disposition. |
| S4-C03 | Acquisition/database/interrupted-load failure is visible; history survives; retry creates no duplicates. | Failure suite exercises timeout/HTTP/database/stage failures and partial status. Database refresh tests prove failed-insert recovery, preservation and retry. An OS/process kill or crash during a multi-stage load was not demonstrated. | E01, E02, E03; [failure tests](../tests/test_ingestion_failure_logging.py), [refresh tests](../tests/test_incremental_refresh.py). | **Partially verified / PARTIAL**; retain interruption/restart evidence. |
| S4-C04 | One expected new game changes only expected records; unexpected volume changes are flagged. | Before/after snapshots prove expected insertion and unchanged historical rows; truncated input does not delete history. No agreed volume-deviation threshold or runtime volume detector exists. | E03; incremental, retry and truncated-input tests. | **Partially verified / PARTIAL**; define and test volume policy. |
| S4-C05 | Failed refresh does not advance last-success time; an agreed freshness threshold identifies stale state. | Expected-game presence is checked per player; missing data is overdue after more than two Eastern-calendar days. Boundary and failed-refresh recovery tests pass. This measures game availability, not run age; there is no persisted last-success timestamp and the threshold is proposed, not team-approved. | E03; [freshness procedure](refresh_freshness_monitoring.md), [monitor](../scripts/check_data_freshness.py). | **Partially verified / PARTIAL**; add actual run metadata and approve threshold. |
| S4-C06 | Manual anomaly review records disposition, rationale, reviewer and escalation. | Review/recovery steps exist and passing-test logs contain synthetic error events. No signed human triage/disposition or actual escalation record was located. The worksheet is a procedure, not completed review evidence. | [Review procedure](ingestion_failure_review.md); [manual worksheet](sprint4_cc7_2_review_worksheet.md). | **Not yet tested / BLOCKED** for the required human review. |
| S4-C07 | Injected failing data assertion causes nonzero pytest/CI and output is retained; required-job gating is coordinated. | Relevant CI steps passed in E05/E06. Earlier run E07 failed at Python collection; it demonstrates failure visibility but is not the planned injected data-assertion test. Data steps are blocking in configuration, but required branch-protection checks were not verified, and report retention has a collision risk. | E05–E07; [workflow](../.github/workflows/ci.yml); gaps F04/F05. | **Partially verified / PARTIAL**; execute a controlled data-step failure and inspect retained files and required checks. |
| S4-C08 | Two generations from identical input/code have matching full SHA-256, with both manifests retained. | Existing dataset tests assert matching hashes for unchanged data and changed hashes for changed data; E04 contains those passing cases. Two separately identified production-like generation manifests for this scenario have not been retained together. | E04; [hash tests](../tests/test_modeling_dataset.py), [dataset validation](../tests/test_modeling_dataset_validation.py). | **Partially verified / PARTIAL**; attach two manifests and input/code identity. |
| S4-C09 | A manual stored/source sample records source/date, field values, results and discrepancy disposition. | ESPN excerpts and research samples exist. They do not by themselves prove a manual comparison against the stored database. Earlier Sprint 3 notes contain illustrative/uncompleted wording and are not accepted as dated Sprint 4 verification. | [Source excerpts](samples/espn_feature_responses.json); [manual worksheet](sprint4_cc7_2_review_worksheet.md). | **Not yet tested / BLOCKED**; perform and sign the stored/source comparison. |

## 4. Evidence register: what was actually checked

Local XML files were parsed during this documentation task; all four report
hashes match the [machine-readable manifest](evidence/cc7-2/evidence_manifest.json).
The reports record earlier executions, not new test runs performed for this
documentation change. Full SHA-256 values, timestamps, module counts, PR SHAs,
CI step metadata, and artifact metadata are retained in that manifest.

| ID | Evidence / stable link | Actual result | Provenance / limits |
| --- | --- | --- | --- |
| E01 | [Failure/related tests, local XML](evidence/ingestion-failure-tests.xml) | 60 tests, 0 failures/errors/skips; includes 32 failure simulations. | November 2 local Python 3.11; remaining 28 cases are related parser/ESPN/game-log regressions. No live provider outage. |
| E02 | [Anomaly/integrity/idempotency, local XML](evidence/ingestion-anomaly-review.xml) | 54 tests, 0 failures/errors/skips: 35 anomaly, 13 integrity, 6 idempotency/roster tests. | November 2 disposable PostgreSQL 18, project schema and deterministic seed. Not production data. |
| E03 | [Refresh/freshness, local XML](evidence/refresh-freshness.xml) | 21 tests, 0 failures/errors/skips: 15 offline threshold/command cases and 6 PostgreSQL refresh cases. | November 2; connection-local temporary tables and actual upserts; no permanent test-data changes. |
| E04 | [Full Python regression, local XML](evidence/refresh-full-regression.xml) | 251 tests, 0 failures/errors/skips. | Includes E03 and other tests; do not add report counts together as unique cases. Scikit-learn artifact/runtime version warnings were noted in the source review. |
| E05 | [Merged-main CI run 41556385360](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41556385360) | Completed **success** at `870f02c`; failure logging, anomaly, refresh, data-regression and project-test steps individually report success. | GitHub API metadata inspected. Individual CI test counts and report contents were not inspected. |
| E06 | [Freshness-branch CI run 41555957615](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41555957615) | Completed **success** at `20320ce`; relevant data steps individually report success. | Confirms the resolved freshness branch was exercised. Metadata, not a downloaded console transcript. |
| E07 | [Earlier failed ingestion-branch run 41553839487](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41553839487) | Overall **failure**; failure-logging and anomaly/data steps passed, Python project step failed. | Supplied log identified import and merge-marker collection errors. Preserve as failed history; later E05/E06 supersede it, rather than rewriting it as a pass. |
| E08 | [Proposal Google Doc](https://docs.google.com/document/d/1l8euXlMGXi-CjAZtP_0K2UOqW0aluzsx/edit) and [GitHub capture manifest](evidence/cc7-2/evidence_manifest.json) | Original nine scenarios inspected; selected PR/run metadata saved; local XML hashes verified. | Proposal is a mutable external document; export hash identifies the inspected version. |

For external submission, immutable existing-evidence URLs follow this pattern:
`https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/870f02cedac548d809b680b9f1ebeceed1161abb/docs/evidence/refresh-freshness.xml`.
The manifest contains a complete stable URL for each local report. After this
package is committed, use its own commit SHA for links to the assessment and
worksheet; do not invent a URL before that commit exists.

### CI artifact retention finding

The API lists `test-results-140` for E05, expiring December 3, 2026 UTC. It was
reported as only **230 bytes**. An attempted download returned HTTP 401, so its
contents are **not verified** and this assessment does not claim it contains the
JUnit files. Artifact existence and upload success are insufficient proof of
report preservation.

Configuration review identifies a concrete risk: pytest writes JUnit files into
`test-results/` before the Playwright step, while `playwright.config.js` supplies
no separate output directory. Playwright documents that its default output
directory is `test-results/` and is cleaned at startup
([official configuration documentation](https://playwright.dev/docs/api/class-testconfig#test-config-output-dir)).
Thus this workflow configuration can remove the earlier Python reports. The
small artifact supports investigating that risk but does not prove its exact
contents. F04 records the remediation and required verification.

The workflow also references summary step IDs that are not assigned and allows
backend tests to continue on error. E05's backend step itself passed, so no
failure is concealed in that particular inspected run; the configuration issue
still matters for future runs. No CI configuration was changed in this task.

## 5. Automated and manual procedures

Use a disposable migrated/seeded database for database suites. Configure
`DATABASE_URL` privately; never attach `.env` or raw connection errors. Retain the
date/time zone, commit, fixture, environment, command, actual status and report
hash for each execution. Setup details:
[data test setup](sprint3_data_testing.md).

| Procedure | Command / method | Pass/fail and retained evidence |
| --- | --- | --- |
| A01 — anomalies | `python -m pytest tests/test_pipeline_anomalies.py -v --junitxml=assessment-results/anomalies.xml` | All valid fixtures pass; injected corrupt fixtures are identified; populated stored-data audit has no unexplained offending rows. Retain XML and any sanitized record identities. |
| A02 — ingestion failures | `python -m pytest tests/test_ingestion_failure_logging.py -v --junitxml=assessment-results/failures.xml -o junit_logging=all` | Expected failure classes are logged safely; commands return nonzero for incomplete runs; no credential sentinels are emitted. Retain XML/logs. |
| A03 — preservation and freshness | `python -m pytest tests/test_data_freshness.py tests/test_incremental_refresh.py -v --junitxml=assessment-results/refresh.xml -o junit_logging=all` | Expected-date policy and full-row before/after checks pass, including failed update/retry. Retain XML and scope. |
| A04 — deterministic datasets | `python -m pytest tests/test_modeling_dataset.py tests/test_modeling_dataset_validation.py -v --junitxml=assessment-results/datasets.xml` | Hash/schema tests pass. Separately generate twice and retain both manifests to complete S4-C08. |
| M01 — anomaly disposition | Follow [worksheet M01](sprint4_cc7_2_review_worksheet.md). Inspect an actual captured synthetic error and an anomaly query result, classify routine failure/defect/possible security event, explain rationale and record reviewer/escalation. | Not executed as a signed human review in available evidence. Blank fields remain pending. |
| M02 — stored/source comparison | Follow worksheet M02; read selected stored player-games and compare fields with retained trusted source samples. | No API contract testing; record each stored/source value and discrepancy disposition. Pending Sprint 4 execution. |
| M03 — CI evidence and gating | Inspect E05/E06 step outcomes; authenticate to download the report artifact, enumerate expected XML files, verify they parse and record hashes. Coordinate a deliberate failing **data** assertion in a disposable branch with Jacob. | Metadata inspection completed; content inspection and injected data-gate verification pending. Do not intentionally break main. |

`assessment-results/` above deliberately separates proposed evidence output from
Playwright's default directory. It is a suggested local collection path, not a
claim that the current workflow uploads that directory. Do not overwrite earlier
reports when preserving an assessment trail.

Freshness policy: an expected appearance missing **more than two Eastern-calendar
days** after its game date is overdue; delay equal to two days is pending. Pending
emits WARNING and returns 0, while an overdue gap emits ERROR and returns 1.
Supply a confirmed player appearance date, not an assumed daily schedule. The
policy is documented and tested but still requires team approval. Detailed
signals and limitations: [freshness monitoring](refresh_freshness_monitoring.md).

## 6. Gaps and Sprint 5 follow-up work

These are **proposed work items**, not newly created Jira tickets or assigned
commitments. Caden owns SEC-04; teammate roles are recommended coordination
partners. Replace local gap IDs with actual Jira links after the team creates or
links the work.

| ID / priority | Gap and evidence | Sprint 5 action / proposed owner | Closure evidence |
| --- | --- | --- | --- |
| F01 — High | No persisted run ID, UTC start/end/source/outcome or last-success metadata; C03/C05 only partly demonstrated. | Caden: add run records and distinguish attempted, partial, failed and successful refreshes; test interruption/restart. | Failed run leaves prior last-success unchanged; process interruption and safe restart are demonstrated with logs, before/after state and PR/CI links. |
| F02 — High | No deployed monitoring cadence, confirmed escalation reviewer, alert delivery or reviewed security-event decision. | Caden with designated reviewer: agree cadence/retention/escalation; run an end-to-end scheduled failure and signed triage. | Alert delivered to agreed owner, dated acknowledgement, classification/rationale and disposition recorded. Test a monitor that stops running as well as one that detects bad data. |
| F03 — Medium | Two-day freshness grace is proposed; expected-game selection is manual; volume thresholds are absent. | Caden with Data/Analytics owner: approve freshness/volume policies and derive expectations from eligible completed appearances. | Approved rules plus healthy/off-day/DNP/sparse-season, stale-load and unexpected-volume tests; false-positive review. |
| F04 — High | Report-directory collision and unverified 230-byte CI artifact; upload success does not establish XML preservation. | Coordinate with Jacob: separate Python evidence from Playwright output, preserve reports on failure, and inspect an authenticated artifact. | Artifact contains named failure/anomaly/refresh XML files after Playwright completes and after a failed run; parsed counts/hashes recorded. |
| F05 — High | Required checks unverified; no deliberate failed data-assertion CI proof; summary IDs are unset and backend errors may continue. | Jacob with Caden: verify branch protection and relevant gate behavior; correct reporting; test an isolated data-suite failure. | Nonzero data step blocks the required check; valid report is retained; summary accurately reflects outcomes. |
| F06 — Medium | S4-C08 lacks two retained generation manifests; S4-C09 lacks a dated stored/source worksheet. | Caden: retain both run manifests and input/code identity; complete manual source comparisons. | Full matching SHA-256 values, two manifest references and signed field-level sample/discrepancy records. |

No baseline, retention duration or anomaly-review SLA is claimed as agreed until
the team records approval. Local pytest proves controlled behavior, not sustained
operating effectiveness across the sprint or deployment.

## 7. Submission checklist for the Google Doc

The required submission is a **Google Doc link**, not only a repository PR.
Use the supplied proposal as a continuation, or create a separate interim
assessment and cross-link it. Preserve headings/tables when copying this content.

- [ ] Add this assessment to the Google Doc and confirm evaluator access without
  broadening sharing beyond the course's requirements.
- [ ] Include all five personal PR links above, this documentation PR, and any
  additional Sprint 4 work not visible in the inspected repository history.
- [ ] Include the supporting runbooks, manual worksheet, local XML reports,
  machine-readable manifest and verified CI run links.
- [ ] Add individual Jira URLs for failure logging, freshness monitoring and this
  evidence task, alongside SCRUM-102, SCRUM-108, SCRUM-115 and the board link.
- [ ] Link actual Sprint 5 Jira items for F01–F06 once created/agreed; until then,
  label them proposed rather than completed.
- [ ] Retain **PARTIALLY VERIFIED** overall status, exact per-scenario outcomes,
  actual results, missing evidence and remaining work. Do not relabel pending
  human review or run metadata as passed because automated tests are green.
- [ ] Verify GitHub report links and archive CI content before artifact expiry;
  obtain the designated reviewer's sign-off where required.

The document package is ready for review, but the Google Doc update, missing
issue links, manual sign-off and operational follow-ups remain explicit work.
