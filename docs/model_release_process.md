# Model approval and rollback (SEC-05)

The served model is the single entry with `"status": "approved"` in `ml/models/registry.json`. `ml/predict_player.py` loads only that model, only through the verify-before-load loader, and fails closed (no prediction) if zero or several models are approved.

**Rules**
- **Manifests and registry entries are generated, never hand-written.** Only `save_model` (in `ml/model_integrity.py`) and the one-time `ml/backfill_model_registry.py` create them.
- **Status changes only through the command line:** `python ml/model_integrity.py set-status` or `python ml/model_release.py rollback`.
- **No performance threshold for approval.** The baseline comparison must be *shown* in the PR, but a model doesn't have to beat it.

## Approve a new model

1. [ ] **Train and save.** Run `python -m ml.training.train_tree_points`. It saves the model with `save_model` and registers it as `candidate`; nothing is served yet.
2. [ ] **Create a branch:** `git switch -c approve/<version>`
3. [ ] **Approve:** `python ml/model_integrity.py set-status <version> approved`. This also moves the previously approved model back to `candidate`.
4. [ ] **Confirm the switch:** run `python ml/model_release.py verify`. It must show `"consistent": true` and the new version.
5. [ ] **Commit** the model file, its manifest, and `registry.json`.
6. [ ] **Open a PR to `main`.** Paste the output of `python ml/model_release.py summary <version>` as the PR description; it holds the validation results and the baseline comparison.
7. [ ] **Get a review.** A reviewer other than the author approves the PR, and CI passes.
8. [ ] **Merge.** The approval takes effect in the merged `registry.json`.

## Roll back a failed upgrade

1. [ ] **Find both versions:** `python ml/model_integrity.py list`. Note the failed model (currently `approved`) and the previous one (`candidate`).
2. [ ] **Create a branch:** `git switch -c rollback/<failed-version>`
3. [ ] **Roll back:** `python ml/model_release.py rollback <failed-version> <previous-version>`. This command:
   - approves the previous model;
   - sets the failed one to `rejected`;
   - loads the approved model exactly as the predictor does;
   - exits non-zero unless the loaded `model_version` equals the restored registry entry and its manifest, and the file's SHA-256 matches the manifest.
4. [ ] **Save the output.** Keep the rollback command's JSON output as evidence, for the PR and in `docs/evidence/`.
5. [ ] **Commit `registry.json`** and open a PR with the reason for the rollback and the JSON output. Get a review, pass CI, and merge.
