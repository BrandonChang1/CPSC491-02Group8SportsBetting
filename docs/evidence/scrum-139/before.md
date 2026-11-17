# PostgreSQL Query Performance

PostgreSQL 18.6 (Homebrew); median of 50 `EXPLAIN (ANALYZE, BUFFERS)` runs after one warm-up; sample player `201939`.

Rows: players 5185, games 1252, player_game_stats 5047, ingestion_refresh_runs 0  
Indexes: `games_date_teams_unique`, `games_pkey`, `player_game_stats_pkey`, `players_pkey`, `teams_abbreviation_key`, `teams_pkey`

| Query | Median ms | Max ms | Rows | Buffers | Scans | Result hash |
|---|---|---|---|---|---|---|
| player search (typeahead) | 1.734 | 3.429 | 1 | 48 | Seq Scan on players | `17f6a592157114e7` |
| player search (common term) | 1.982 | 3.028 | 10 | 48 | Seq Scan on players | `add31d094047d2c3` |
| player list search | 1.555 | 2.284 | 47 | 48 | Seq Scan on players | `349f5d33e47da980` |
| player details | 0.02 | 0.049 | 1 | 4 | Index Scan on players_pkey<br>Seq Scan on teams | `ba965551ca9b379d` |
| recent game log | 0.311 | 0.613 | 100 | 23 | Index Scan on player_game_stats_pkey<br>Seq Scan on games | `875b033b058c189e` |
| paged game history | 0.052 | 10.33 | 10 | 33 | Index Scan on games_date_teams_unique<br>Index Scan on player_game_stats_pkey | `563e19d47c39f6ad` |
| points history (prediction) | 0.206 | 0.487 | 113 | 23 | Index Scan on player_game_stats_pkey<br>Seq Scan on games | `94d6e8c2e933e6c9` |
| points + minutes history | 0.171 | 0.247 | 113 | 23 | Index Scan on player_game_stats_pkey<br>Seq Scan on games | `790c8cc5699f7573` |
| team recent records | 4.783 | 7.089 | 27 | 238 | Seq Scan on games<br>Seq Scan on player_game_stats<br>Seq Scan on teams | `4398b24b22234787` |
| team rotation estimates | 10.326 | 11.199 | 2492 | 286 | Seq Scan on games<br>Seq Scan on player_game_stats<br>Seq Scan on players<br>Seq Scan on teams | `b9b3f9dee4ea4795` |
| modeling/readiness dataset | 2.942 | 3.278 | 5047 | 236 | Seq Scan on games<br>Seq Scan on player_game_stats | `e95995552b8243e6` |
| database freshness | 0.011 | 0.015 | 1 | 1 | Seq Scan on ingestion_refresh_runs | `3740ed8f4867b6d5` |

Used by:

- player search (typeahead): `backend/app/services/fastPlayerLookup.js searchPlayersInDatabase`
- player search (common term): `backend/app/services/fastPlayerLookup.js searchPlayersInDatabase`
- player list search: `backend/app/routes/players.js GET /players?search=`
- player details: `backend/app/routes/players.js GET /players/:id`
- recent game log: `backend/app/services/fastPlayerLookup.js getPlayerStatsFromDatabase`
- paged game history: `backend/app/routes/players.js GET /players/:id/games`
- points history (prediction): `backend/app/services/prediction.js`
- points + minutes history: `backend/app/routes/predictions.js`
- team recent records: `backend/app/services/teamWinPrediction.js`
- team rotation estimates: `backend/app/services/treeTeamPrediction.js`
- modeling/readiness dataset: `data/processing/prediction_readiness.py`
- database freshness: `backend /health/freshness, incremental_refresh --status`
