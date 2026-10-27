# ESPN NBA ingestion

ESPN supplies player rosters, teams, regular-season game logs, box scores, team
history, and schedules. No runtime code imports `nba_api`. Existing PostgreSQL
primary keys, backend history queries, cleaned DataFrame columns, and modeling
features are preserved.

## Endpoints

All requests use HTTPS, a 15-second timeout, HTTP status checks, and JSON validation.
These public ESPN endpoints do not require an API key:

| Purpose | URL / parameters |
| --- | --- |
| Teams | `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams?limit=100` |
| Current roster | `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_team_id}/roster` |
| Player game log | `https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{espn_player_id}/gamelog?season=2025` |
| Box score | `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}` |
| Team history | `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_team_id}/schedule?season=2025&seasontype=2` |
| Schedule | `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={YYYYMMDD}` |

ESPN labels seasons by their ending year: `2024-25` becomes `2025`. Only the
exact Regular Season game-log category is included; preseason, play-in, and
playoff categories are excluded. Box scores must be final and regular-season.
The prediction fallback reads points directly from game logs, avoiding a box-score
request per game. Full ingestion reads box scores for offensive/defensive rebounds
and plus-minus, which the athlete game log omits. Missing/malformed statistics
raise errors instead of fabricating zeros. Zero shooting attempts yield a zero
percentage; other shooting percentages are calculated as fractions to three decimal
places. Game dates use the Eastern calendar day so after-midnight UTC tipoffs match
NBA-era records. Minutes are rounded to the nearest whole minute (half up) to preserve the SQL schema.
Schedules fetch one Eastern-calendar date at a time with six workers; ESPN NBA scoreboards reject
date ranges. The requested window is bounded to the existing 14-day lookahead.

## Identity and existing records

- `data/collection/legacy_nba_ids.json` freezes the player names/IDs and 30 team
  identities from the previously installed `nba_api==1.11.4` static catalog. It
  contains no game statistics and needs no NBA network requests. Keep this frozen
  to preserve identities already assigned during the transition.
- `data/collection/espn_player_ids.json` records 436 legacy-player-to-ESPN mappings
  checked against ESPN rosters on October 26, 2026. Unique names are compared after
  accent, punctuation, and case normalization, retaining suffixes. Brandon Williams
  is explicitly mapped to NBA `1630314` / ESPN `4397040`; NBA `1585` is a different
  person with the same name. Existing explicit mappings take precedence over names.
- New ESPN-only players use `9000000000 + ESPN athlete ID`, a positive BIGINT range
  separate from legacy NBA IDs. Unknown legacy IDs fail with a clear error. Add a
  verified mapping for an older/retired player before retrieving their ESPN history;
  existing stored history stays available through the backend without ESPN.
- Team abbreviations such as `GS`, `NY`, and `UTAH` become `GSW`, `NYK`, and `UTA`.
  All teams retain their original NBA database IDs. Unknown teams are rejected.
- New game IDs are `espn:{event_id}`. Before either game or stat ingestion, a game
  is reconciled by date plus home/away team IDs. An existing NBA game ID wins, so
  ESPN stats upsert into the existing `(player_id, game_id)` row. Conflicting or
  ambiguous identities are rejected. Migration `004_unique_game_identity.sql`
  also enforces uniqueness of that natural game identity for concurrent writes.

No historical rows are deleted. Normal ingestion can update statistics for an
existing player/game through the established upsert behavior. If migration 004
finds pre-existing duplicate games, it stops; reconcile those records manually
without discarding their stats before retrying.

## Run and verify

From the repository root, with the project's Python environment activated:

```sh
pip install -r requirements.txt
npm run migrate
python -m data.ingestion.database_ingestion
python -m data.ingestion.historical_backfill
```

The first ingestion command loads current teams/players and Curry's 2025-26 game
logs. The existing backfill command retains its 2024-25 season and 5,000-row target.
Set `DATABASE_URL` for the intended database before running these write operations.
To make read-only sample requests, use `python -m scripts.test_nba_api`.

GitHub Actions validates controlled ESPN JSON fixtures and runs the database
regression suite against its PostgreSQL service. It makes no live NBA or ESPN
requests. Fixture files in `tests/fixtures/espn_*.json` are reduced ESPN response
samples: the game log and box score describe Curry's April 13, 2025 game
(`401705764`), with an added duplicate event/category to exercise filtering.

```sh
python -m pytest tests/test_espn.py tests/test_nba_game_logs.py -v
# Full suite: use a disposable PostgreSQL database, apply migrations and seed it first.
python -m pytest
```

## Remaining limits

ESPN's public JSON response shapes and availability can change. Network errors
surface to callers; backfill logs failed players and can safely be rerun. Full
historical ingestion makes one box-score request per game (cached within the
process), so large backfills are slower than the lightweight prediction fallback.
Current-roster searches do not list every retired player. Retired-player ESPN
retrieval needs an explicit ID mapping; stored database history does not. New
unmapped athletes with ambiguous legacy names are rejected until reviewed.
The unique game index cannot automatically repair duplicates created before
this migration. Deployments must include the collection module and its JSON
identity catalogs alongside scripts.
