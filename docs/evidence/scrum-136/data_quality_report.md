# NBA Database Data-Quality Report

Generated: 2026-11-17T00:26:30+00:00  
Result: **PASS**  
Games stored: 2024-10-22 to 2026-04-12

## Summary

| Metric | Value |
|---|---|
| teams rows | 30 |
| players rows | 5185 |
| games rows | 1252 |
| player_game_stats rows | 5047 |
| Checks run | 32 |
| Checks passed | 31 |
| Failed error checks | 0 |
| Failed warning checks | 1 |
| Stat records checked | 5047 |
| Invalid stat records (fail any error check) | 0 |
| Duplicate groups | 0 |

## Checks

| Category | Severity | Check | Rows checked | Failing | Result |
|---|---|---|---|---|---|
| duplicates | error | one stat row per player per game | 5047 | 0 | pass |
| duplicates | error | one stat row per player per game date | 5047 | 0 | pass |
| duplicates | error | one game per date and team pair (either home/away order) | 1252 | 0 | pass |
| duplicates | error | one game per team per date | 2504 | 0 | pass |
| duplicates | warning | player names map to one player ID among players with stats | 84 | 0 | pass |
| missing | error | stat row has player_id and game_id | 5047 | 0 | pass |
| missing | error | game has game_date, home_team_id and away_team_id | 1252 | 0 | pass |
| missing | error | player has full_name | 5185 | 0 | pass |
| missing | error | stat row has minutes, points, rebounds and assists | 5047 | 0 | pass |
| missing | error | stat row has opponent_team_id and is_home | 5047 | 0 | pass |
| missing | warning | stat row has matchup and win_loss | 5047 | 0 | pass |
| numeric | error | counting stats are not negative | 5047 | 0 | pass |
| numeric | error | minutes within 0-70 | 5047 | 0 | pass |
| numeric | error | points within 0-100 | 5047 | 0 | pass |
| numeric | error | rebounds within 0-60 | 5047 | 0 | pass |
| numeric | error | assists within 0-40 | 5047 | 0 | pass |
| numeric | error | made shots do not exceed attempts | 5047 | 0 | pass |
| numeric | error | shooting percentages within 0-1 | 5047 | 0 | pass |
| numeric | warning | shooting percentages equal made / attempted | 5047 | 0 | pass |
| numeric | error | points equal 2*FGM + 3PM + FTM | 5047 | 0 | pass |
| numeric | error | rebounds equal offensive + defensive rebounds | 5047 | 0 | pass |
| numeric | warning | points, rebounds and assists are zero when minutes are zero | 5047 | 1 | warn |
| numeric | error | recent_minutes_avg is a non-negative number | 5047 | 0 | pass |
| relationships | error | stat row's player exists | 5047 | 0 | pass |
| relationships | error | stat row's game exists | 5047 | 0 | pass |
| relationships | error | stat row's opponent team exists | 5047 | 0 | pass |
| relationships | error | opponent and is_home agree with the game's teams | 5047 | 0 | pass |
| relationships | error | matchup's team abbreviation is one of the game's teams | 5047 | 0 | pass |
| relationships | error | game's home and away teams exist and differ | 1252 | 0 | pass |
| relationships | error | player's current team exists | 5185 | 0 | pass |
| relationships | error | stat rows are for games on or before today | 5047 | 0 | pass |
| relationships | warning | every stored game has at least one stat row | 1252 | 0 | pass |

## Sample failing rows

Up to 5 per check.

### points, rebounds and assists are zero when minutes are zero (warning, 1 rows)

- `{"player_id": "1628396", "game_id": "0022400942"}`
