## M02 — Stored/source comparison (S4-C09)

1. Choose a small, explained sample of actual stored eligible player-game rows.
   Include at least one refreshed record and one preserved historical record;
   document the sample selection. The proposal sets no numerical sample minimum,
   so record the size agreed with the reviewer rather than inventing approval.
2. Retain a read-only SQL result/export of the stored fields. Map internal player,
   team and legacy game IDs to the source identities explicitly. A source research
   CSV is not a substitute for a stored-database result.
3. Use a retained trusted source record, such as the
   [ESPN response excerpts](../../../samples/espn_feature_responses.json), after confirming
   it refers to the same appearance. Compare points, minutes, shooting counts,
   opponent and home/away fields as appropriate. This is a data comparison, not
   endpoint/network/API-contract verification.
4. Document transformations: percentages 0–100 versus 0–1, minute rounding,
   Eastern-calendar dates and reconciled identities. Record any discrepancy,
   expected transformation or unresolved defect; do not silently adjust values.
5. Attach source capture date/hash, stored export/hash, query, environment,
   observed result, discrepancy disposition and human sign-off.

### Review record

| Field | Value |
| --- | --- |
| Executor / date | Caden Santiago / 2026-11-02 (stored export and source capture 2026-11-03T02:18Z) |
| Environment | Local development PostgreSQL (`localhost`, database `sports_betting_test`), read-only `SELECT`; no credentials recorded |
| Code revision | `95d53aa52fa0587e511a46964b401f30824219ae` (branch `feature/validate-prop-prediction-dataset`) |
| Reviewer | PENDING |

### Sample selection

Player: Stephen Curry (stored `player_id` 201939 = ESPN athlete 3975, per
`data/collection/espn_player_ids.json`). He is the only player with stored
2025-26 rows, so he is the only player with both a preserved and a refreshed
record.

- **Preserved historical record:** 2025-04-13 vs LAC (game `0022401198` = ESPN
  event `401705764`). This is the only player-game in the retained ESPN excerpts.
- **Refreshed record:** 2025-10-21 @ LAL (game `0022500002` = ESPN event
  `401809244`). This is Curry's first stored 2025-26 game.

Sample size: 2 player-games, 20 field comparisons. The proposal sets no minimum,
so the size is PENDING reviewer agreement.

Identities were matched by player, Eastern game date and teams. Team IDs:
LAC = stored `1610612746` = ESPN team 12; LAL = stored `1610612747` = ESPN team 13.

### Results

| Player/game and identity mapping | Source reference/capture date | Field | Actual stored value | Source value / normalization | PASS/FAIL/BLOCKED and explanation | Reviewer/date |
| --- | --- | --- | --- | --- | --- | --- |
| Curry 201939 = ESPN 3975 / 0022401198 = ESPN 401705764 | Retained excerpt `espn_feature_responses.json` (gamelog season=2025), retrieved 2026-10-27T01:31:43Z | game date | 2025-04-13 | 2025-04-13T19:30Z → 2025-04-13 Eastern | PASS — same date after UTC→Eastern | PENDING |
| same | same | home/away | `is_home` = true | `atVs` = "vs", homeTeamId 9 (GS) | PASS | PENDING |
| same | same | opponent | LAC (1610612746) | ESPN team 12 (LAC) | PASS — IDs reconciled | PENDING |
| same | same | minutes | 38 | 38 | PASS | PENDING |
| same | same | points | 36 | 36 | PASS | PENDING |
| same | same | FG made-attempted | 10-20 | 10-20 | PASS | PENDING |
| same | same | FG % | 0.5 | 50.0 → 0.500 (0–100 to 0–1) | PASS — expected transformation | PENDING |
| same | same | 3PT made-attempted | 7-12 | 7-12 | PASS | PENDING |
| same | same | 3PT % | 0.583 | 58.3 → 0.583 | PASS — expected transformation | PENDING |
| same | same | FT made-attempted | 9-9 | 9-9 | PASS | PENDING |
| Curry 201939 = ESPN 3975 / 0022500002 = ESPN 401809244 | New capture `espn_gamelog_3975_season2026.json`, 2026-11-03T02:18:09Z | game date | 2025-10-21 | 2025-10-22T02:00Z → 2025-10-21 22:00 Eastern | PASS — same date after UTC→Eastern | PENDING |
| same | same | home/away | `is_home` = false | `atVs` = "@", homeTeamId 13 (LAL) | PASS | PENDING |
| same | same | opponent | LAL (1610612747) | ESPN team 13 (LAL) | PASS — IDs reconciled | PENDING |
| same | same | minutes | 32 | 32 | PASS | PENDING |
| same | same | points | 23 | 23 | PASS | PENDING |
| same | same | FG made-attempted | 6-14 | 6-14 | PASS | PENDING |
| same | same | FG % | 0.429 | 42.9 → 0.429 | PASS — expected transformation | PENDING |
| same | same | 3PT made-attempted | 3-9 | 3-9 | PASS | PENDING |
| same | same | 3PT % | 0.333 | 33.3 → 0.333 | PASS — expected transformation | PENDING |
| same | same | FT made-attempted | 8-8 | 8-8 | PASS | PENDING |

### Transformations and limitations

- Percentages: ESPN uses 0–100 with 1 decimal; stored values use 0–1 with 3 decimals.
- Dates: ESPN gives UTC timestamps; stored dates are the America/New_York calendar date.
- Minutes: both sources are whole minutes, so no rounding difference was observed.
- The local database has no `ingestion_refresh_runs` table (migration 005 not
  applied). "Refreshed" therefore means a stored 2025-26 row, not a logged
  refresh run.
- The 2025-26 source was captured live on 2026-11-03. Its hash identifies that
  response only; ESPN could serve different data later.
- This is a data comparison, not endpoint/network/API-contract verification.

### Evidence

| File | SHA-256 |
| --- | --- |
| [m02_stored_query.sql](m02_stored_query.sql) (read-only query) | `30af204683b890142099938e1044b0dc84a32045221dac4ad62b12fbef385ac6` |
| [m02_stored_export.csv](m02_stored_export.csv) (stored export, `psql \copy`) | `4ef8068e787d24eb675a4d88e04095db0ce894525280885e1aa0052f9c4fa1c7` |
| [espn_gamelog_3975_season2026.json](espn_gamelog_3975_season2026.json) (full response from `https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/3975/gamelog?season=2026`, HTTP 200) | `20782d0bc761311b944bc6bdaba5ec99af632baa152c49a7e143971400169148` |
| [espn_feature_responses.json](../../../samples/espn_feature_responses.json) (retained excerpts) | `fccea9a92d5e9f24f2f66a2b566a11e7328767752eafe2a9b4a7ed9840f3af08` |

### Disposition and sign-off

| Item | Value |
| --- | --- |
| Observed result | 20 of 20 fields match after the documented transformations |
| Discrepancies | None found |
| Reviewer name / date | PENDING |
| Reviewer decision (PASS / FAIL / BLOCKED) | PENDING |
| Sample size agreed? | PENDING |