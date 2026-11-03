# SEC-05 negative-test evidence (SCRUM-111, SCRUM-113)

**Date:** 2026-10-26 · **Branch:** `swayam` · **Suite:** `tests/test_model_integrity.py`
**Raw output:** [pytest_output.txt](pytest_output.txt) (43 passed) · [backend_api_test_output.txt](backend_api_test_output.txt) (1 passed)

Every test builds its own small model and approved manifest in pytest's `tmp_path` (`tests/conftest.py`), then breaks one thing. Each negative test asserts three things:

1. The loader raises the specific exception.
2. The artifact was **never deserialized**: a spy on `joblib.load` records zero calls.
3. `predict_player.predict()` fails closed: `success: false`, the matching `errorCode`, no `predictedPoints` or `modelVersion`, and no server paths or hashes in the message.

| # | Case | How it is broken | Expected rejection | Actual result |
|---|------|------------------|--------------------|---------------|
| 1 | Modified artifact: bit flipped | Last byte XOR 1 | `ModelHashMismatchError` (`hash_mismatch`) | Rejected, 0 loads, no prediction: **PASS** |
| 2 | Modified artifact: byte appended | `+ b"\x00"` | `ModelHashMismatchError` | **PASS** |
| 3 | Modified artifact: truncated | Last 16 bytes removed | `ModelHashMismatchError` | **PASS** |
| 4 | Swapped-in loadable model | Valid bundle with a changed intercept, saved under the approved manifest | `ModelHashMismatchError` | **PASS** |
| 5–12 | Incomplete manifest: one field missing | Each of the 8 required fields removed in turn | `IncompleteManifestError` (`manifest_incomplete`), naming that field | **PASS** (8 of 8) |
| 13 | Incomplete manifest: several problems | 1 field missing, 2 empty, 1 blank feature dtype | `IncompleteManifestError` listing all 4 problems | All 4 reported: **PASS** |
| 14 | Unparseable manifest | `{not json` | `IncompleteManifestError` | **PASS** |
| 15 | Missing manifest | Manifest file deleted | `ManifestMissingError` (`manifest_missing`) | **PASS** |
| 16–20 | Incompatible feature schema | Reordered; `is_home` dtype changed; feature removed; extra feature added; feature renamed | `FeatureSchemaMismatchError` (`feature_schema_mismatch`) | **PASS** (5 of 5) |
| 21 | Bundle features disagree with manifest | Valid manifest and hash, but the bundle's own feature order is reversed | `FeatureSchemaMismatchError`, raised after the bytes are verified and before the model is returned | **PASS** |
| 22–25 | Incompatible model_version | `…-v2`; `…-v0.9.0`; `random-forest-points-v1`; malformed `…-points-1` | `IncompatibleModelVersionError` (`incompatible_model_version`) | **PASS** (4 of 4) |

**Positive controls (same fixtures):**
- An approved model loads and returns `VerifiedModel` with the manifest's version (1 deserialization).
- `predict()` returns a prediction with `modelVersion` equal to the manifest's `linear-regression-points-v1.2.0`.

**Do the tests catch real failures?** I disabled the hash comparison in `load_verified_model`: cases 1–4 failed. I disabled the schema comparison: cases 16–20 failed. Both checks were restored afterward.

## Prediction API (SCRUM-113)

- `tests/test_prediction_model_version.py` (3 passed):
  - `predict()` and the spawned `ml/predict_player.py` process (as Express runs it) both return `modelVersion` equal to the committed manifest's `model_version`.
  - With a fixture manifest, the version follows the manifest, not a hardcoded value.
- `backend/tests/predictionsApi.test.js` (1 passed): the real `GET /api/players/:id/prediction` route, with only the database stubbed, returns 200 and `modelVersion === manifest.model_version`.
- Sample responses, captured with [capture_api_response.js](capture_api_response.js):

| Case | File | Result |
|------|------|--------|
| Approved model | [sample_prediction_response.json](sample_prediction_response.json) | `200`, `modelVersion: "linear-regression-points-v1"`, matching the approved manifest |
| Tampered model (one bit flipped, in a scratch copy of the code) | [sample_prediction_response_tampered_model.json](sample_prediction_response_tampered_model.json) | `503`, `errorCode: "hash_mismatch"`, no `predictedPoints` or `modelVersion` |

## Reproduce

```
python -m pytest -v tests/test_model_integrity.py tests/test_prediction_model_version.py tests/test_predict_player.py
npm test    # includes backend/tests/predictionsApi.test.js; set PYTHON_COMMAND if python3 lacks requirements.txt
```
