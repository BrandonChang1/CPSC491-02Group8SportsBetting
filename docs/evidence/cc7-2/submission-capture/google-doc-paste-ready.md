# Sprint 4 Interim SOC 2 Compliance Assessment

**Owner:** Caden Santiago — Data & Storage  
**Control:** SEC-04 — Data pipeline integrity and failure monitoring, aligned to CC7.2  
**Assessment date:** November 2, 2026 (Pacific)  
**Overall assessment:** PARTIALLY VERIFIED

## Scope and acceptance criteria

My assessment covers ingestion failures, PostgreSQL integrity, safe retries, stale-data detection, and retained test evidence. Brandon owns SEC-03 API integrity and security, including endpoint verification, response contracts, and API-dependent betting behavior. API exceptions are simulated here to verify ingestion failure handling.

The failure-logging task requires detectable simulated failures, credential-safe failure records, a documented anomaly review procedure, and captured test results.

## Procedures and actual results

I used deterministic fixtures to simulate timeouts, HTTP errors, database connection errors, rejected rows, incomplete stages, empty game histories, and post-processing failures. Tests verify failure counters, diagnostic events, command exit status, and continued processing where supported. Credential-safety checks inject synthetic secret-bearing exception messages and assert that password, token, username, host, and traceback information are absent from captured output.

A fresh local run on November 2 produced **32 passed, 0 failures, 0 errors, 0 skipped; pytest exit status 0**. These are passing failure-handling simulations, not successful live ingestion attempts. No live ESPN requests or database writes were needed for this suite. The baseline was `e4369bb6170f4114e8d370b177abd823394c27f3`; local working-tree changes were present. The retained capture metadata identifies the checked code files and report hash.

Command: `python -m pytest tests/test_ingestion_failure_logging.py -v --junitxml=assessment-results/failures.xml -o junit_logging=all`

Actual sanitized diagnostic examples from the run:

```
ingestion_failed command=test_ingestion_failure_logging error_type=Timeout
ingestion_failed command=test_ingestion_failure_logging error_type=HTTPError
ingestion_failed command=data.ingestion.database_ingestion error_type=OperationalError
```

| Task acceptance criterion | Actual evidence and result |
| --- | --- |
| Simulated API or ingestion failure is detectable | VERIFIED for controlled cases: 32 passing tests cover acquisition/database errors, row failures, incomplete stages and command results. |
| Failure information is recorded without exposing credentials | VERIFIED for tested error paths: secret-sentinel and traceback assertions passed; logs retain diagnostic type/context. |
| Anomaly review procedure is documented | DOCUMENTED: the runbook explains capture, classification, safe recovery, integrity checks and follow-up. A signed human disposition/escalation record remains pending. |
| Results are captured as compliance evidence | CAPTURED: fresh console/JUnit output, committed prior reports, PRs, CI status and screenshots are retained. CI archive contents have not been authenticated and inspected. |

## Supporting evidence

Previously retained November 2 reports independently record:

- [Failure and related regression report — 60 passed, including the same 32 failure scenarios](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/870f02cedac548d809b680b9f1ebeceed1161abb/docs/evidence/ingestion-failure-tests.xml).
- [Anomaly, integrity and idempotency report — 54 passed](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/870f02cedac548d809b680b9f1ebeceed1161abb/docs/evidence/ingestion-anomaly-review.xml).
- [Freshness and historical preservation report — 21 passed](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/870f02cedac548d809b680b9f1ebeceed1161abb/docs/evidence/refresh-freshness.xml).
- [Full Python regression report — 251 passed](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/870f02cedac548d809b680b9f1ebeceed1161abb/docs/evidence/refresh-full-regression.xml).

These reports overlap and must not be added together as unique tests. Only the 32-case failure suite was rerun for this evidence capture.

[GitHub Actions run 41556385360](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41556385360) completed successfully for commit `870f02c`. Its failure-logging, anomaly and refresh/preservation steps show success. The screenshot demonstrates step status, not individual CI test counts or downloadable report contents.

Supporting documentation:

- [Ingestion failure logging and anomaly review procedure](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/e4369bb6170f4114e8d370b177abd823394c27f3/docs/ingestion_failure_review.md).
- [Refresh and freshness procedure](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/e4369bb6170f4114e8d370b177abd823394c27f3/docs/refresh_freshness_monitoring.md).
- [Detailed assessment and scenario matrix](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/e4369bb6170f4114e8d370b177abd823394c27f3/docs/sprint4_cc7_2_compliance_assessment.md).
- [Manual assessment worksheet — template, not completed sign-off](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/blob/e4369bb6170f4114e8d370b177abd823394c27f3/docs/sprint4_cc7_2_review_worksheet.md).

## Anomaly review and remaining work

The documented review sequence is to capture the command/status and sanitized logs; identify the affected stage and classify the condition; inspect partial writes; retry the affected scope without deleting valid history; run the integrity/anomaly checks; and retain the disposition and reviewer evidence. Potential security events are escalated to the designated reviewer once that role is confirmed.

The overall control remains **PARTIALLY VERIFIED**. Controlled tests establish detection and recovery behavior, but do not demonstrate sustained monitoring or complete operational effectiveness. Remaining work includes a signed anomaly review, confirmed escalation contact, approved thresholds, deployed checks/alert delivery, verified report retention, persisted run/last-success metadata and interruption/restart evidence. Two retained dataset-generation manifests and a completed manual stored/source worksheet are also still needed for the broader proposal. Work in progress is not treated as verified evidence.

## Sprint 4 pull requests and Jira

- [PR #78 — ESPN ingestion migration](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/78), supporting data-ingestion work — [SCRUM-108](https://csu-group-8.atlassian.net/browse/SCRUM-108).
- [PR #80 — Data pipeline anomaly detection](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/80) — [SCRUM-102](https://csu-group-8.atlassian.net/browse/SCRUM-102).
- [PR #81 — ESPN feature/data availability research](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/81), related sprint work — [SCRUM-115](https://csu-group-8.atlassian.net/browse/SCRUM-115).
- [PR #88 — Ingestion failure logging and anomaly review](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/88) — ADD INDIVIDUAL JIRA LINK.
- [PR #90 — Refresh and freshness monitoring](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/90) — ADD INDIVIDUAL JIRA LINK.
- [PR #93 — Sprint 4 SEC-04 CC7.2 assessment evidence](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/93) — ADD INDIVIDUAL JIRA LINK.

Jira issue contents/status were not independently verified. Confirm the course sprint date range and add any other personal Sprint 4 contributions before submitting.

## Screenshot captions

**Figure 1. Local failure-logging verification.** A browser-rendered view of the actual retained local JUnit/console output shows 32 passing simulations, sanitized error events and exit status 0. This is a local report view, not a CI console screenshot. Insert `local-failure-tests.png` here.

**Figure 2. GitHub Actions ingestion checks.** Actual GitHub Actions job page for run 41556385360 shows successful failure-logging, anomaly and freshness/preservation steps. Insert `ci-data-checks.png` here and retain the run link above.
