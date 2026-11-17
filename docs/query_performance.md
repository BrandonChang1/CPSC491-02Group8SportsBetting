# PostgreSQL Query Performance Testing and Optimization (SCRUM-139)

## How to run

```sh
python -m scripts.query_performance                       # Markdown report
python -m scripts.query_performance --runs 50 --output docs/evidence/scrum-139/after.md
python -m scripts.query_performance --json
```

- Read-only: it runs inside `SET TRANSACTION READ ONLY` and only issues `SELECT` / `EXPLAIN ANALYZE SELECT`.
- The backend SQL is read directly from the JS source files, so the benchmark
  measures what the API actually runs. If a query is edited so it can't be found,
  the script and `tests/test_query_performance.py` fail.
- Each query runs under `EXPLAIN (ANALYZE, BUFFERS)` once to warm up, then
  `--runs` more times. The report shows the median and max execution time, the
  scans used, buffers touched, and a SHA-256 of the returned rows (in order), so
  results can be compared before and after a change.
- The sample player is the one with the most stored games.

## Queries evaluated

| Query | Where it runs | How often |
|---|---|---|
| Player search (typeahead) | `fastPlayerLookup.searchPlayersInDatabase` (`server.js` search) | Every keystroke |
| Player list search | `GET /players?search=` | Per search |
| Player details | `GET /players/:id` | Per player view |
| Recent game log | `fastPlayerLookup.getPlayerStatsFromDatabase` | Per player view |
| Paged game history | `GET /players/:id/games` | Per page |
| Points history | `services/prediction.js`, `routes/predictions.js` | Per prediction |
| Team recent records | `services/teamWinPrediction.js` | Upcoming-games page |
| Team rotation estimates | `services/treeTeamPrediction.js` | Upcoming-games page |
| Modeling/readiness dataset | `data/processing/prediction_readiness.py` (same shape as `modeling_dataset.py`) | Training / readiness runs |
| Database freshness | `GET /health/freshness`, `incremental_refresh --status` | Monitoring |

## Indexes reviewed

| Index | Serves |
|---|---|
| `player_game_stats_pkey (player_id, game_id)` | Every per-player history query (leading `player_id`) |
| `games_pkey (id)` | Joins from stats to games |
| `games_date_teams_unique (game_date, home_team_id, away_team_id)` | Game reconciliation during ingestion; also used for date ordering in paged history |
| `players_pkey`, `teams_pkey`, `teams_abbreviation_key` | ID / abbreviation lookups |
| `ingestion_refresh_runs_scope (player_id, season, id DESC)` | Per-scope freshness |

Not added, because no frequent query needs them:
- `player_game_stats(game_id)`: no hot query filters stats by game; joins go stats → games through `games_pkey`.
- `players(team_id)`: only used in the team-rotation aggregate, which reads every row anyway.

## Findings (development database, PostgreSQL 18.6, 5,185 players / 1,252 games / 5,047 stat rows)

1. **Bottleneck: player search scanned the whole `players` table.**
   - `full_name ILIKE '%term%'` has a leading wildcard, which a B-tree index can't serve.
   - Every keystroke read all 5,185 rows (48 buffers, about 1.7–2.0 ms).
   - **Fixed** with a `pg_trgm` GIN index.
2. **Per-player history queries are already indexed.**
   - They use `player_game_stats_pkey` and run in 0.02–0.3 ms.
   - The planner hashes the small `games` table instead of probing `games_pkey`, which is cheaper at this size.
   - It switches to index lookups by itself as `games` grows. No change made.
3. **Team aggregates scan the full stats table by design.**
   - Team recent records takes about 4.5 ms, team rotation estimates about 10.5 ms.
   - Both rank every active player's games with window functions, so they have to read every row; an index wouldn't help.
   - **Scaling risk:** cost grows linearly with stored history. If many seasons are loaded and these get slow, cache the result per day or limit `historical` to recent seasons. That changes behavior, so it needs a team decision first.
4. **Modeling dataset (about 2.8 ms)** reads every row intentionally.
5. **Found while checking results: unstable search ordering.**
   - `GET /players?search=` ordered by `full_name` alone. Ties (e.g. two players named "Mike James") had no defined order, so with `OFFSET`/`LIMIT` paging a tied player could appear on two pages or on none.
   - Added `id` as a tiebreaker there and in the typeahead query.

## Optimization applied

`database/migrations/006_player_name_search_index.sql` (also in `database/schema.sql`):

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS players_full_name_trgm ON players USING gin (full_name gin_trgm_ops);
```

- `pg_trgm` ships with PostgreSQL. It's a trusted extension (PostgreSQL 13+), so the database owner can create it without being a superuser.
- Search terms shorter than 3 characters can't use trigrams. For those, the planner keeps the sequential scan, which is still correct.

## Before and after (median of 50 runs)

Full reports: `docs/evidence/scrum-139/before.md` (before migration 006 and the tiebreaker) and `docs/evidence/scrum-139/after.md`.

| Query | Before ms | After ms | Plan change | Results identical |
|---|---|---|---|---|
| Player search, typeahead (`lebron`) | 1.734 | 0.026 | Seq Scan → Bitmap Index Scan on `players_full_name_trgm` (48 → 10 buffers) | Yes |
| Player search, common term (`james`) | 1.982 | 0.064 | Seq Scan → Bitmap Index Scan (48 → 31 buffers) | Yes |
| Player list search (`james`) | 1.555 | 0.094 | Seq Scan → Bitmap Index Scan | Yes (same rows and order) |
| All other queries | | | No plan change; differences are run-to-run noise | Yes |

Results are compared using the SHA-256 of the ordered rows, and all 12 queries
match. For the list search, the same 47 rows were also confirmed with the index
disabled (`enable_bitmapscan = off`).

## Verification

- `tests/test_query_performance.py`: every backend query is still found; the report runs read-only; the trigram index exists and is usable for `ILIKE`.
- Full Python suite (349) and backend `npm test` (76) pass with migration 006 applied.

## Limitations

- The timings come from a small local database, so absolute numbers will differ in CI and production. The plan changes (which scan is used) are what carry over.
- Benchmarks for the backend queries depend on the marker strings in `scripts/query_performance.py`. If a query is rewritten, update its marker. The test fails until you do.
