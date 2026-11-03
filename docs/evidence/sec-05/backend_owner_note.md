# SEC-05 note for the backend owner (SCRUM-113)

**What already works (no backend change made):**
- `GET /api/players/:id/prediction` (`backend/app/routes/predictions.js`) spawns `ml/predict_player.py`.
- That script now loads the model only through the verify-before-load loader.
- It returns `modelVersion` from the approved manifest.
- It fails closed with `success: false` and an `errorCode`, which the route already turns into a 503.
- Covered by `backend/tests/predictionsApi.test.js`.

**Decisions and small changes that are yours. I didn't make them:**

1. **Log Python stderr.** On an integrity failure, `predict_player.py` prints the full detail (file path, expected vs. actual hash) to stderr and exits 0. The client gets only a safe message and `errorCode`. `executePython` discards stderr when the exit code is 0, so the detail is lost. Suggested change, in the `close` handler before `resolve(...)`:
   ```js
   if (stderr.trim()) console.warn(`${scriptName} stderr:`, stderr.trim());
   ```
2. **Second prediction endpoint.** `GET /players/:id/prediction` (`backend/app/services/prediction.js`) is the JS last-5 average baseline. It reports a hardcoded `model_version: "baseline-last5-v1"` and loads no model file, so manifests don't apply to it. The frontend calls the `/api/...` route. Please decide whether to retire it or label it clearly as a non-ML baseline, so the two version fields aren't confused.
3. **Field name for Group 2.** The API returns `modelVersion` (camelCase, the existing contract used by `public/player-search.html`). The Python loader exposes `VerifiedModel.model_version`. Please confirm with Group 2 which name they read from the API before anyone renames or duplicates the field.
4. **CI enforcement.** A failing backend test, including `predictionsApi.test.js`, currently can't fail CI:
   - The "Run backend automated tests" step has `continue-on-error: true`.
   - `.github/workflows/ci.yml` ends with a "Run this last … Remove this step" comment but no step under it.
   - The test steps have no `id:`, so the summary's `steps.*_tests.outcome` values are empty.

   The Python pytest step has no `continue-on-error`, so the new SEC-05 pytest files *do* fail CI. The API test needs `python3` with `requirements.txt` installed, which CI already does earlier in the same job.
