## Model approval: `random-forest-points-v1.1.0`

- Current status: `approved` · created 2026-11-03T01:02:13.484130+00:00 · commit `b03bc82` (worktree clean: not recorded)
- Model SHA-256 `ac6b2b3b839c4cb5fdc35537977b9933e4caaf148683e0370b4db90433c273c2`
- Dataset `player_game_stats_sample_features_3df1c9ab3d07` (SHA-256 `3df1c9ab3d07…`)

### Validation results

| Check | Result |
|---|---|
| Manifest complete | pass  |
| Model file matches manifest SHA-256 | pass |
| Registry entry matches manifest version | pass |
| Loads through the secure loader with the predictor's version and feature schema | pass |

### Baseline comparison (same held-out rows; informational, not an approval threshold)

Held-out period: 2025-03-13 → 2026-04-12, 1002 rows, 77 players.

| Model / baseline | n | MAE | RMSE | R² |
|---|---|---|---|---|
| **random-forest-points-v1.1.0** | 1002 | 5.77 | 7.383 | 0.517 |
| Season avg | 1002 | 5.73 | 7.456 | 0.508 |
| Last 5 avg | 1002 | 5.82 | 7.644 | 0.483 |
| Last 10 avg | 1002 | 5.673 | 7.36 | 0.52 |

Best baseline: Last 10 avg. Model beats it on MAE: no.
