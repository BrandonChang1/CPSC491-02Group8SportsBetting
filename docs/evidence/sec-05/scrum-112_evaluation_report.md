# SCRUM-112 (SEC-05): Training and evaluation review

**Date:** 2026-11-02 · **Branch:** `swayam` · **Model:** random forest points model (`ml/training/train_tree_points.py`)
**Data:** `data/sample/player_game_stats_sample_features.csv` (SHA-256 `3df1c9ab3d07…`), 84 players

## Summary

- **Splits are chronological.** No future data reaches training, and the committed training features recompute exactly from raw logs using earlier games only.
- **The one-player holdout is fixed.** Test now covers **1,002 rows from 77 players**, up from 42 rows of one player.
- **Same rows for everyone.** The baseline and the model are scored on identical held-out rows, and the code enforces it.
- **The baseline comparison is informational.** On the new holdout the random forest scores MAE **5.770** vs **5.673** for the best baseline (Last 10 avg). Approval does not require beating a baseline or meeting any score.
- **The evaluated model is approved and served** as `random-forest-points-v1.1.0` (SHA-256 `ac6b2b3b…`).

## 1. Chronological split audit

| Check | Finding |
|---|---|
| Features use only earlier games | Pass. `pts_*` features use `shift(1)`; `recent_minutes_avg` uses `shift(1).rolling(5)`. New test: every feature in the committed training CSV equals a recomputation from `player_game_stats_sample.csv` (0 differences across 5,047 rows). |
| Train ends before test | Pass, before and after the change. Old split: train ≤ 2025-10-21 < test ≥ 2025-10-23. New split: train ≤ 2025-03-12 < test ≥ 2025-03-13. No date is in both. |
| Imputer and model fit on train only | Pass. One pipeline is fit on `holdout.train`. |
| Hyperparameters chosen without the test set | Pass. `train_tree_points.py` uses fixed parameters; nothing is tuned on the holdout. |

No chronology violation was found, so no leakage fix was needed. The problem was the *size and coverage* of the test set.

## 2. The one-player holdout issue

**What it was.** The training notebooks already documented it: the CSV's precomputed `split` column comes from `time_split(train_fraction=0.8)`, which cuts at 80% of *unique dates*. Here the last ~20% of dates are Stephen Curry's 2025-26 season, the only player with 2025-26 data. So the test set was **42 rows from 1 player**, and the reported test metrics described one player, not the model.

**Fix.**
- `time_split(..., by="rows")` puts the cutoff at the last date where train still holds ≤ 80% of rows, and never splits a date. The default stays `by="dates"`, so the notebooks and other callers are unchanged.
- `ml/training/evaluation.py` ignores the CSV's `split` column and builds the holdout with `by="rows"`.
- It raises `HoldoutError` if the test set covers fewer than **10 players** (`MIN_TEST_PLAYERS`) or if train doesn't end before test.

| Holdout | Train | Test | Test players |
|---|---|---|---|
| Old (CSV `split` column) | 4,920 rows | 42 rows, 2025-10-23 → 2026-04-12 | 1 |
| **New** (`holdout_split`) | 3,960 rows, 84 players, 2024-10-24 → 2025-03-12 | **1,002 rows, 2025-03-13 → 2026-04-12** | **77** |

The new test set has 960 rows from 77 players in late 2024-25, plus Curry's 42 rows from 2025-26.

## 3. Baseline and model use the same held-out rows

This is enforced in `ml/training/evaluation.py`:
- **One eligibility rule.** `holdout_split` keeps only rows that have `points` and all three baseline features, and that rule applies to train and test alike. Before, the baseline notebook and the training script dropped different rows (4,920 vs 4,921 train).
- **Baselines can't drift.** `score_holdout(test, predictions)` builds the baseline predictions from the same `test` frame it scores the model on. It raises `HoldoutError` if any prediction set has a different index or length.
- **The scored model is the approved model.** `save_model` writes the model, its manifest (with these metrics) and its registry entry in one step, so the metrics always belong to that exact model file. Approval is a registry status change; there is no score threshold.

## 4. Results on the new holdout (`random-forest-points-v1.1.0`, trained on the new train split)

| Model / baseline | n | MAE | RMSE | R² |
|---|---|---|---|---|
| **Random forest** (test) | 1,002 | **5.770** | 7.383 | 0.517 |
| Last 10 avg (best baseline) | 1,002 | **5.673** | 7.360 | 0.520 |
| Season avg | 1,002 | 5.730 | 7.456 | 0.508 |
| Last 5 avg | 1,002 | 5.820 | 7.644 | 0.483 |
| Random forest (train) | 3,960 | 3.594 | 4.756 | 0.797 |

**By season (test):**

| Season | Rows | Random forest MAE | Last 10 avg MAE |
|---|---|---|---|
| 2024-25 (77 players) | 960 | 5.654 | 5.563 |
| 2025-26 (Curry only) | 42 | 8.409 | 8.179 |

**Reading the results:**
- The forest is 0.097 points worse in MAE than the last-10 average, and is about level on RMSE and R².
- Train MAE (3.594) is far below test MAE (5.770), which points to overfitting (`min_samples_leaf=4`).
- The old one-player test MAE (8.114 for the notebook forest) overstated the model's error for most players. It mostly measured how unpredictable one player's season was.

Recorded in the model's manifest (`evaluation_metrics`, `training_config`) and summarized in `ml/models/registry.json`. *Updated for SCRUM-109/110: the earlier `random_forest_points.evaluation.json` and `generate --evaluation` command were replaced by `save_model`.*

## 5. Split and leakage tests

`docs/evidence/sec-05/scrum-112_leakage_tests_output.txt`: **45 passed, 0 failed.**

| File | Tests | Status |
|---|---|---|
| `tests/test_time_split.py` (existing) | 12 | Pass |
| `tests/test_points_features.py` (existing) | 8 | Pass |
| `tests/test_modeling_features.py` (existing) | 4 | Pass |
| `tests/test_modeling_dataset_validation.py` (existing) | 10 | Pass |
| `tests/test_training_evaluation.py` (**new**, one per gap found) | 11 | Pass |

The new tests cover:
- the row-weighted split;
- a regression test for the one-player holdout;
- refusing a holdout with too few test players;
- the baseline and model scored on identical rows;
- predictions for other rows rejected;
- the committed training features recomputing from earlier games only;
- the evaluation record being self-consistent;
- the manifest generator refusing metrics from a different model file.

The full CI-scope Python suite passes (212 tests).

## Known limitations

- **The served model is slightly worse than the last-10 average** on this holdout (MAE +0.097). By decision, approval has no score requirement. Possible improvements are regularization or more features, tuned with time-series CV on the train set only.
- **The served model trains on less recent data.** `v1.1.0` is trained only on games through 2025-03-12, so that the model that was evaluated is the one served. The previous `v1` used all of 2024-25, but it couldn't be fairly evaluated.
- **Evaluation is more optimistic than serving.** The holdout uses the true `is_home` and recent minutes. At serving time, `predict_player.py` passes `is_home` as unknown (it is imputed), and the minutes may be missing.
- **The test period mixes two seasons.** Late 2024-25 for 77 players, plus one player's 2025-26. This is reported per season above. Multi-player data covers one season only.
- **Not yet updated:** the notebooks, `ml/EDA/baseline_metrics.csv` and the `*_metrics.csv` files still use the CSV's one-player split. The linear regression model wasn't re-evaluated. The CSV's `split` column still exists, but `evaluation.py` ignores it.
- **Small sample:** 84 players and one season.
