# SEC-05 evidence record: ML model integrity (SCRUM-109 to SCRUM-114)

**Recorded:** 2026-11-03 · **Updated:** 2026-11-03, after PRs #94 and #97 merged · **Repo:** `BrandonChang1/CPSC491-02Group8SportsBetting` · **Process:** [docs/model_release_process.md](../../model_release_process.md)

**Status rule:** **PASS** = merged to `main` and backed by CI or recorded evidence. **BLOCKED** = implemented and verified, but not yet merged to `main`, or waiting on someone else. **FAIL** = the control is not operating.

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Model changes require a reviewed GitHub PR before approval | **FAIL** | `main` is not branch-protected (GitHub API `branches/main`: `"protected": false`), so nothing enforces review or CI. [PR #87](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/87) was approved at 00:27:48Z. Merge commits `a4db5ae` (00:31:47Z) and `2af8531` (00:37:16Z) were added *after* that approval. The PR was merged at 00:37:31Z, while [CI run 41554165361](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41554165361) was still running; that run failed ("Run Python project tests"). `2af8531` bypassed model verification and was fixed in [PR #89](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/89). It happened again with [PR #94](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/94): approved at 01:36:50Z and merged at 01:40:01Z, while its [CI run 41561216796](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41561216796) had failed at "Run Python linting". Every later step, including all test steps, was skipped, so #94's tests never ran in CI before merge. [PR #97](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/97) fixed the lint error. |
| 2 | Model approval includes validation results and baseline comparison | **PASS** | `python ml/model_release.py summary <version>` generates the approval summary. The summary for the served model ([scrum-114_approval_summary_random-forest-points-v1.1.0.md](scrum-114_approval_summary_random-forest-points-v1.1.0.md)) was committed in reviewed [PR #94](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/94). `test_approval_summary_has_validation_results_and_baseline_section` passes in [CI run 41562487108](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41562487108) (push to `main`). Note: #94 committed the summary as a file. Its PR description is empty, so the summary was not used as the PR body. |
| 3 | A failed upgrade can be rejected and the previous approved model restored | **PASS** | Rollback drill on `save_model` fixtures: [scrum-114_rollback_drill.json](scrum-114_rollback_drill.json) (failed model → `rejected`, previous → `approved`, all 4 checks `true`). Tests `test_rollback_*` (`tests/test_model_release.py`) are in [scrum-114_test_output.txt](scrum-114_test_output.txt) and pass in [CI run 41562487108](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41562487108). The drill JSON is a local run; the tests are the CI evidence. |
| 4 | Rollback verification confirms the correct model version is loaded | **PASS** | In the same drill, the loaded version equals the restored registry entry and its manifest, the file SHA-256 matches the manifest, and a prediction reports the restored `modelVersion`. `rollback` exits non-zero otherwise. Same tests and CI run as #3. |
| 5 | Test results, manifests, hashes, PR links and CI evidence are recorded | **PASS** | This record. All SEC-05 work is merged (PRs #87, #89, #94, #97), and each PR's review and CI result is linked below. The hashes below match `main` at `7b04ed4`. |
| 6 | Each SEC-05 criterion is marked PASS, FAIL or BLOCKED with evidence | **PASS** | This table. |
| 7 | Approved models load successfully | **PASS** | `test_approved_model_loads_and_predicts`. [CI run 41555268920](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41555268920) (PR #89): "Run Python project tests" passed. Served model verified: [scrum-114_served_model_verification.json](scrum-114_served_model_verification.json). |
| 8 | Modified model files are rejected when hashes don't match | **PASS** | `test_modified_artifact_is_rejected_before_deserialization` (3 variants), `test_swapped_in_loadable_model_is_rejected`; same CI run. Tampered-model API response: 503 `hash_mismatch` ([sample_prediction_response_tampered_model.json](sample_prediction_response_tampered_model.json)). |
| 9 | Missing manifest fields prevent model loading | **PASS** | `test_manifest_missing_a_required_field_is_rejected` (all 8 fields), `test_incomplete_manifest_reports_every_problem`; same CI run. |
| 10 | Incompatible model versions or feature schemas are rejected | **PASS** | `test_incompatible_model_version_is_rejected` (4), `test_incompatible_feature_schema_is_rejected` (5); same CI run. |
| 11 | Failed verification prevents the model from generating predictions | **PASS** | Every negative test also asserts that `predict()` returns `success: false` with no `predictedPoints`; same CI run. See [negative_test_evidence.md](negative_test_evidence.md). |
| 12 | The prediction API returns the correct model_version, matching the approved manifest | **PASS** | `test_spawned_prediction_process_reports_the_approved_model_version` (CI run above). `backend/tests/predictionsApi.test.js` passed locally ([backend_api_test_output.txt](backend_api_test_output.txt)); CI can't confirm it because that step has `continue-on-error`. Sample: [sample_prediction_response.json](sample_prediction_response.json). The open items in [backend_owner_note.md](backend_owner_note.md) don't affect this result. |

**Totals:** 11 PASS · 1 FAIL · 0 BLOCKED.

**Note on CI for 2–12:** "Run Python project tests" passed on `main` after #97 merged ([CI run 41562487108](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41562487108), commit `659a056`). That run covers the merged registry-based loader, approval and rollback tests. The local run is in [scrum-114_test_output.txt](scrum-114_test_output.txt): 87 SEC-05 tests, 233 in the full suite. CI excludes `tests/test_modeling_dataset_validation.py`, so the 10 dataset-validation tests in [scrum-112_leakage_tests_output.txt](scrum-112_leakage_tests_output.txt) are local evidence only.

## Pull requests and CI

| PR | Scope | Review | CI |
|---|---|---|---|
| [#87](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/87) | SCRUM-109, 110, 111, 113 (`bdf2e84`, `9ea84d8`) | [Approved](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/87#pullrequestreview-5745368035) by cadensantiagoat, *before* merge commits were added | [41554165361](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41554165361): **failure** (merged anyway) |
| [#89](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/89) | Fix for the merge that bypassed verification (`fd24f4e`) | [Approved](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/89#pullrequestreview-5745509512) by cadensantiagoat | [41555268920](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41555268920): success; push to `main` [41555646333](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41555646333): success |
| [#94](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/94) | SCRUM-112 evaluation, SCRUM-109/110 registry, SCRUM-114 approval/rollback process (`dc551d4`) | [Approved](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/94#pullrequestreview-5745986204) by cadensantiagoat | [41560781204](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41560781204): **failure** at lint, tests skipped; push to `main` [41561216796](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41561216796): **failure** (same; merged anyway) |
| [#97](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/97) | Lint fix for #94 (`bf012d4`) | [Approved](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/pull/97#pullrequestreview-5746150353) by cadensantiagoat | [41562283787](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41562283787): success; push to `main` [41562487108](https://github.com/BrandonChang1/CPSC491-02Group8SportsBetting/actions/runs/41562487108): success |

## Registered models and hashes (SHA-256)

| Model (registry status) | Model file | Manifest file |
|---|---|---|
| `random-forest-points-v1.1.0` (**approved**) | `ac6b2b3b839c4cb5fdc35537977b9933e4caaf148683e0370b4db90433c273c2` | `3cec9d8d83f0c9bd710d8f7a1855b15fc4bf6859fdf71340a70b5e08bc18bbe8` |
| `linear-regression-points-v1` (candidate) | `c6bfdad2ea27c7bea04191c6427336478b4f437f372d700f02bec5aced98cace` | `8dc55dcc6b609537a66f2610695e605781f5e76e4762a9684ed02d9835c9cad5` |

`ml/models/registry.json`: `dd868ef4ba69a69ae7cc52cd2a14eccaab23c3206fc2e85229c3cdd80e60d858`. Training data `player_game_stats_sample_features.csv`: `3df1c9ab3d0722ce2daa222bf39f5c740a6349f9e4980c3d02fdf95898e156f7`.

## Files in this folder

| File | What it shows |
|---|---|
| [scrum-114_test_output.txt](scrum-114_test_output.txt) | 87 SEC-05 tests and the full suite (233), all passing |
| [scrum-114_rollback_drill.json](scrum-114_rollback_drill.json) and [run_rollback_drill.py](run_rollback_drill.py) | Rollback drill output, and the script to reproduce it |
| [scrum-114_approval_summary_random-forest-points-v1.1.0.md](scrum-114_approval_summary_random-forest-points-v1.1.0.md) | Approval PR body for the served model |
| [scrum-114_served_model_verification.json](scrum-114_served_model_verification.json) | Which model is served, cross-checked against registry, manifest and hash |
| [scrum-112_evaluation_report.md](scrum-112_evaluation_report.md) and [scrum-112_leakage_tests_output.txt](scrum-112_leakage_tests_output.txt) | Holdout and leakage review |
| [negative_test_evidence.md](negative_test_evidence.md), [pytest_output.txt](pytest_output.txt), [backend_api_test_output.txt](backend_api_test_output.txt), `sample_prediction_response*.json` | SCRUM-111/113 negative tests and API responses |
| [backend_owner_note.md](backend_owner_note.md) | Open backend items |
