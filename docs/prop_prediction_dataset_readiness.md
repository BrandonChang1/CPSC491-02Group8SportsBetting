# Sprint 4 Prop-Prediction Dataset Readiness

## Purpose

Validates that the PostgreSQL dataset has the fields and historical context
the Sprint 4 points over/under workflow needs. Shared with the Prediction &
Analytics teammate as the data contract for the points model.

## How to run

```
python -m data.processing.prediction_readiness
```

Read-only: one `SELECT` against `player_game_stats` joined to `games`. It
prints a JSON report and exits `1` if any check fails, so it can gate a
training run. Tests: `tests/test_prediction_readiness.py`.

## Required points-prediction fields

The served model is `random-forest-points` (`ml/predict_player.py`,
`EXPECTED_FEATURE_SCHEMA`). It is trained by `ml/training/train_tree_points.py`.

| Model input | dtype | Built from stored field(s) | Built by |
|---|---|---|---|
| `pts_season_avg` | float64 | `points`, `game_date` | `add_points_features` (prior games this season) |
| `pts_last5_avg` | float64 | `points`, `game_date` | `add_points_features` (prior 5 games) |
| `pts_last10_avg` | float64 | `points`, `game_date` | `add_points_features` (prior 10 games) |
| `is_home` | bool | `player_game_stats.is_home` | stored at ingestion |
| `recent_minutes_avg` | float64 | `minutes`, `game_date` | `recalculate_recent_minutes_avg` (prior 5 games) |
| target `points` | numeric | `player_game_stats.points` | stored at ingestion |

Also required: `player_id`, `game_id`, `game_date` (ordering and grouping),
and `opponent_team_id` (stored and validated, but **not** a model input yet).

## Opponent, home/away and recent-minutes context

| Context | Used by the model? | Validation |
|---|---|---|
| Opponent | No. Stored for future features. | Present on every row, and equal to the game's other team |
| Home/away | Training: yes. Serving: no. Passed as unknown and imputed, because the next game's venue isn't supplied | Present on every row, and agrees with `games.home_team_id` / `away_team_id` |
| Recent minutes | Training and serving | Recomputed from the prior 5 stored games and compared to the stored value (±0.01). Empty only on a player's first game |

## Completeness and validity checks

| Check | Field | Type |
|---|---|---|
| points present | `points` | completeness |
| points is a whole number 0–100 | `points` | validity |
| minutes present | `minutes` | completeness |
| minutes within 0–70 | `minutes` | validity |
| is_home present | `is_home` | completeness |
| opponent_team_id present | `opponent_team_id` | completeness |
| opponent/home-away agree with the game's teams | `opponent_team_id`, `is_home` | validity |
| recent_minutes_avg present after a player's first game | `recent_minutes_avg` | completeness |
| recent_minutes_avg equals the prior-5-game minutes average (no current-game leakage) | `recent_minutes_avg` | validity |
| recent_minutes_avg empty on a player's first game | `recent_minutes_avg` | validity |
| one row per player per game date | `player_id`, `game_date` | validity |

## Retrieval format

`build_prediction_features` turns the stored rows into the training feature
table using the existing `MODELING_COLUMNS` and `add_points_features`. The
report then compares the result to the served model's `EXPECTED_FEATURE_SCHEMA`
(names and dtypes); any mismatch is listed in `feature_schema_problems` and
makes `ready` false. At serving time, `GET /api/players/:id/prediction` reads
`game_date`, `points`, `minutes` from the same tables and passes them to
`ml/predict_player.py`.

## Results (local database, 2026-11-02)

- `ready: true`. All 11 checks reported 0 failing rows, and there were no feature-schema problems.
- 5,047 player-game rows, 84 players and 30 opponents, from 2024-10-22 to 2026-04-12.
- 4,962 rows have every model input. The other 85 are each player's first
  game, where no prior history exists, plus one first-of-season game.
- All 84 players have at least 10 games.

## Data-quality limitations

1. **Thin current season.** 2025-26 has 43 rows for 1 player; 5,004 rows are
   2024-25. The model is effectively trained on one season, and most
   players' 2025-26 predictions use ESPN fallback history.
2. **No prop lines stored.** The database has no sportsbook points line, so
   the over/under comparison needs the line from another source.
3. **Home/away isn't used at serving time** and opponent isn't a model input.
   Matchup-specific predictions need the upcoming game's venue and
   opponent passed to `predict_player.py` (Prediction & Analytics follow-up).
4. **Minutes are integers.** `player_game_stats.minutes` is `INTEGER`, so partial minutes are lost.
5. **Zero-minute games count.** 17 rows have 0 minutes and are included in
   the points and minutes averages, which pulls them down.
6. **Recent-minutes windows can differ.** Ingestion averages the previous 5
   stored rows; `predict_player.py` averages the last 5 non-null minutes. They
   agree today because no minutes are null. Both windows cross season boundaries.
7. **Training reads a CSV export.** The model was trained on
   `data/sample/player_game_stats_sample_features.csv`, not live Postgres.
   This check confirms the database produces the same feature schema; it
   doesn't prove the CSV matches the current database contents.
8. **Rounding difference.** Training features are rounded to 2 decimals, but
   serving features aren't. The effect is negligible.
9. **No rest, injury or back-to-back context** is stored.
