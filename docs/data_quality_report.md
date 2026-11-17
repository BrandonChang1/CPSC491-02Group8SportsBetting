# NBA Database Data-Quality Report (SCRUM-136)

## Purpose

Checks the NBA PostgreSQL data for missing, duplicate, invalid or inconsistent
player and game-log records before the prediction model uses it.

## How to run

```
python -m data.processing.data_quality_report                 # Markdown to stdout
python -m data.processing.data_quality_report --json          # JSON to stdout
python -m data.processing.data_quality_report --output docs/evidence/scrum-136/data_quality_report.md
```

- Needs `DATABASE_URL` (from `.env`).
- Runs in a `READ ONLY` transaction, so it can be rerun at any time without
  changing stored data.
- Exits `1` if any **error** check fails, `0` otherwise (warnings don't fail it),
  so it can gate a training run or CI step.
- Example report from the development database:
  `docs/evidence/scrum-136/data_quality_report.md`.

## What the report contains

- Row counts for `teams`, `players`, `games`, `player_game_stats`, and the stored game-date range.
- Summary: checks run/passed, failed error and warning checks, stat records checked,
  invalid stat records (distinct rows failing any error check), duplicate groups.
- One line per check: rows checked, failing rows, result.
- Up to 5 sample keys per failing check, to find the rows to fix.

## Checks

| Category | Check | Severity |
|---|---|---|
| duplicates | one stat row per player per game | error |
| duplicates | one stat row per player per game date | error |
| duplicates | one game per date and team pair (either home/away order) | error |
| duplicates | one game per team per date | error |
| duplicates | player names map to one player ID (among players with stats) | warning |
| missing | stat row has `player_id` and `game_id` | error |
| missing | game has `game_date`, `home_team_id`, `away_team_id` | error |
| missing | player has `full_name` | error |
| missing | stat row has `minutes`, `points`, `rebounds`, `assists` | error |
| missing | stat row has `opponent_team_id` and `is_home` | error |
| missing | stat row has `matchup` and `win_loss` | warning |
| numeric | counting stats are not negative | error |
| numeric | minutes 0–70, points 0–100, rebounds 0–60, assists 0–40 | error |
| numeric | made shots ≤ attempts (FG, 3P, FT; 3PM ≤ FGM) | error |
| numeric | shooting percentages within 0–1 and not NaN | error |
| numeric | shooting percentages equal made / attempted (±0.002) | warning |
| numeric | points = 2·FGM + 3PM + FTM | error |
| numeric | rebounds = offensive + defensive rebounds | error |
| numeric | points, rebounds, assists are zero when minutes are zero | warning |
| numeric | `recent_minutes_avg` is non-negative and not NaN | error |
| relationships | stat row's player, game and opponent team exist | error |
| relationships | opponent and `is_home` agree with the game's home/away teams | error |
| relationships | matchup's team abbreviation is one of the game's teams | error |
| relationships | game's home and away teams exist and differ | error |
| relationships | player's current team exists | error |
| relationships | stat rows are for games on or before today | error |
| relationships | every stored game has at least one stat row | warning |
| consistency | `recent_minutes_avg` equals the prior-5-stored-game minutes average (±0.01) | error |
| consistency | teammates in a game agree on `win_loss`, `matchup` and opponent | error |
| consistency | home and away sides of a game have opposite results | error |
| consistency | matchup `vs.` / `@` agrees with `is_home` | error |

Checks skip a row when the fields they compare are `NULL`; missing values are
reported by the "missing" checks instead.

## Findings on the development database (2026-11-16)

- 36 checks (4 consistency checks added in SCRUM-140, see `docs/sprint5_data_fixes.md`), 0 error failures, result **PASS** over 5,047 stat rows, 1,252 games and 5,185 players.
- 1 warning: player `1628396`, game `0022400942` has 0 minutes and 1 rebound.
  Minutes are stored as whole numbers, so a sub-minute stint rounds to 0. This
  is real data, which is why that check is a warning rather than an error.

## Tests

`tests/test_data_quality_report.py` plants bad rows inside a rolled-back
transaction (duplicates, missing fields, invalid numbers, mismatched
relationships) and asserts the report flags each one. It also checks that the
report runs in a `READ ONLY` transaction. It needs the test database. CI runs it in the
"Run data pipeline regression tests" step, then runs the report itself against the
seeded database in the "Run data-quality report" step, which fails the job on any
error-level check.
