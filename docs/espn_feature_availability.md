# ESPN NBA prediction feature availability

Assessment date: October 26, 2026 (Pacific). Live requests were captured during
this assessment; exact UTC capture time, URLs, and response hashes are in the
[response excerpts](samples/espn_feature_responses.json) and
[player-log snapshot](../data/sample/espn_feature_research/source_game_logs.json).

## Findings and recommendation

ESPN provides the raw inputs for eight of the nine requested features. Seven
require calculations over prior appearances; home/away is supplied directly.
Opponent defensive rating was **not found in the sampled team-statistics
responses**. An estimated rating is possible from complete team box scores, but
the application's partial player histories are insufficient to calculate it.
This is a scoped finding, not proof that no ESPN endpoint exposes that metric.

Start with the eight supported features, retain the existing season points
average, and evaluate the additional candidates below using chronological
validation. Defer opponent defensive rating until team-history ingestion or an
official external source can supply values as of each prediction date.

Research produced a [575-row ML CSV](../data/sample/espn_feature_research/points_training.csv),
an [offline rebuild script](../scripts/build_espn_feature_sample.py), and
[feature validation tests](../tests/test_espn_feature_sample.py). No production
ingestion, database schema, or deployed model was changed.

## Requested feature availability matrix

Classification describes the requested feature, not just its underlying stat.
All historical averages must be calculated locally, even when ESPN exposes
season aggregates or unrelated split averages.

| Feature | Priority | Classification | ESPN input / recommended calculation | PostgreSQL inputs |
| --- | --- | --- | --- | --- |
| Last 5 average points | Keep | Derived; supported | `points`; mean of previous up to 5 appearances | `player_game_stats.points`, `player_id`; `games.game_date` |
| Last 10 average points | Keep | Derived; supported | `points`; mean of previous up to 10 appearances | Same as above |
| Last 5 average minutes | High | Derived; supported | `minutes` or summary `MIN`; previous up to 5 appearances | `minutes`, player/game keys, game date |
| Last 5 average FGA | High | Derived; supported | Attempted component of `fieldGoalsMade-fieldGoalsAttempted` / `FG`; previous up to 5 appearances | `field_goals_attempted`, keys/date |
| Last 10 average FGA | High | Derived; supported | Same raw input; previous up to 10 appearances | Same as above |
| Home/away indicator | Medium | Direct; supported | Schedule/summary competitor `homeAway`, or game-log `atVs`; normalize to boolean | `is_home`, `opponent_team_id`; game home/away team IDs |
| Days since last game | Medium | Derived; supported | Target game date minus player's previous appearance date | `games.game_date` joined through player/game keys; upcoming target date at inference |
| Opponent defensive rating | Medium | Unavailable directly in sampled feeds; requires additional processing or another source | Estimated points allowed per 100 possessions from complete team histories; official metric requires a verified source | Proposed `team_game_stats` fields described below; existing player rows alone are insufficient |
| Last 5 average FG% | Medium | Derived; supported | Mean of previous 5 per-game `FGM/FGA` fractions; see percentage policy | `field_goals_made`, `field_goals_attempted`, `field_goal_pct`, keys/date |

## Endpoints and observed fields

These public JSON URLs returned HTTP 200 without an API key during inspection.
They are observed interfaces, not a guaranteed stable public API contract.

| Purpose | Inspected URL | Relevant response fields |
| --- | --- | --- |
| Player game log | [Curry, season 2025](https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/3975/gamelog?season=2025) | Root `names[]` aligns positionally with `seasonTypes[].categories[].events[].stats[]`; event key is `eventId`. Root `events[eventId]` supplies `gameDate`, `homeTeamId`, `awayTeamId`, `atVs`. |
| Summary / player and team box scores | [Event 401705764](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401705764) | `header.season.year/type`; `header.competitions[].date`, `status.type.completed`, `competitors[].id/homeAway/score`. `boxscore.players[].statistics[].labels[]` aligns with `athletes[].stats[]`; `athlete.id`, `didNotPlay`, and `starter` describe the player entry. `boxscore.teams[].statistics[]` has `name` and `displayValue`. |
| Team schedule | [Warriors, season 2025, type 2](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/schedule?season=2025&seasontype=2) | `events[].id/date/season`; `events[].competitions[].competitors[].id/homeAway`; competition status. Returned 82 events in this sample. |
| Historical daily scoreboard | [April 13, 2025](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20250413) | `events[].id/date/season.type`; competition status and competitors. Returned 15 games. |
| Upcoming daily scoreboard | [October 27, 2026](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261027) | Same event and competitor fields are available before the outcome. Four events were `STATUS_SCHEDULED`; date strings can fall on the next UTC day. |
| Team statistics | [Warriors, season 2025](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/statistics?season=2025&seasontype=2) | `requestedSeason.year/type`; `results.stats.categories[].stats[].name/value/displayValue`. Offensive category includes `fieldGoalsAttempted`, `avgFieldGoalsAttempted`, `points`; defensive category contains rebounds, steals and blocks, but no defensive rating. |
| Core team statistics | [Warriors, season 2025, type 2](https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2025/types/2/teams/9/statistics) | `splits.categories[].stats[].name/value`; includes `possessions`, `estimatedPossessions`, `paceFactor`, `trueShootingPct`, and `effectiveFGPct`, but no observed defensive rating or opponent points allowed. |
| Franchise catalog | [NBA teams](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams?limit=100) | `sports[].leagues[].teams[].team.id/abbreviation`; used to reject exhibition teams and map ESPN IDs to the existing NBA IDs. The 30-team mapping is saved with the player snapshot. |

Season parameters use the **ending year**: 2024–25 is `season=2025`, regular
season is type 2. Join statistics by returned names/labels; never assume fixed
array positions. The player log does not have separate FGM/FGA scalar columns:
parse a value such as `10-20` into made and attempted counts.

### Confirmed sample values

For Stephen Curry (`ESPN 3975`, internal player ID `201939`) in event
`401705764` on April 13, 2025:

| Field | Game log | Summary box score | Normalized value |
| --- | --- | --- | --- |
| Points | `points = "36"` | `PTS = "36"` | 36 |
| Minutes | `minutes = "38"` | `MIN = "38"` | 38 |
| Field goals | `fieldGoalsMade-fieldGoalsAttempted = "10-20"` | `FG = "10-20"` | FGM 10; FGA 20 |
| FG% | `fieldGoalPct = "50.0"` | Derived from `FG` | 0.500 |
| Three-pointers | `threePointFieldGoalsMade-threePointFieldGoalsAttempted = "7-12"` | `3PT = "7-12"` | 3PM 7; 3PA 12 |
| Free throws | `freeThrowsMade-freeThrowsAttempted = "9-9"` | `FT = "9-9"` | FTM 9; FTA 9 |
| Venue | `atVs = "vs"`, `homeTeamId = "9"` | Curry's team competitor `homeAway = "home"` | `is_home = 1`; opponent ESPN ID 12 |

Game-log percentages are on the 0–100 scale; database fractions are on 0–1.
The CSV recomputes per-game FG% from made/attempted counts and rounds to three
decimals, matching the current box-score parser. Team-statistics percentages
also need unit checks: the core feed has differently named fraction and percent
fields; do not normalize solely by numeric magnitude.

## Feature calculation contract

For a training row representing game `t`, the label `points` is scored in game
`t`. Every performance feature uses only appearances before `t`. For inference,
use the same definitions on appearances completed before the target tipoff.

- Sort by player and game date. Deduplicate `(player_id, game_id)` first. The
  sample rejects multiple appearances on a player's same Eastern date instead
  of guessing an order; a wider dataset needs stored tipoff timestamps.
- Points, minutes, FGA, and FG% averages: shift one row within each player,
  then take the requested rolling window. Windows cross season boundaries to
  match the existing `add_points_features` implementation. Season points average
  resets each season and also excludes the target game.
- Average available history with `min_periods=1`; no prior appearances means
  NULL/blank, not zero. `prior_games_count` exposes short-history rows. For a
  strict last-10 experiment, filter to `prior_games_count >= 10` consistently.
- `days_since_last_game` is the Eastern-calendar difference from the player's
  previous appearance, so consecutive-day appearances yield 1. It is not the
  number of off-days (difference minus 1), nor necessarily team rest when the
  player missed games. The first appearance is NULL. Long injury/offseason
  gaps remain uncapped in this sample.
- `fg_pct_last5_avg` is the arithmetic mean of previous per-game fractions,
  including 0 when FGA is 0 to match the existing ingestion convention. A pooled
  alternative, `sum(FGM)/sum(FGA)`, weights high-attempt games more heavily and
  is a different feature. Do not silently interchange them. A zero pooled
  denominator should be NULL.
- `is_home` refers to the **target matchup**, never the previous game. At
  inference obtain target event date/opponent/venue from the schedule. A
  hypothetical next game without an identified matchup must retain missing
  context. Designated home status does not establish home-court advantage at a
  neutral venue; a future production export should preserve `neutralSite` too.
- Use only completed eligible games; exclude DNPs, preseason, play-in, playoffs,
  and exhibitions for this regular-season model. A played zero-point game is
  still a valid appearance. Missing/malformed stats are errors, not zero scores.

Illustrative SQL window for an already deduplicated player-game relation:

```sql
AVG(points) OVER (
    PARTITION BY player_id ORDER BY game_date, game_id
    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
) AS pts_last5_avg
```

The offline rebuild reuses `data/processing/points_features.py` for points
features; it adds the research features without changing the shared production
feature list. For each held-out game, earlier completed held-out appearances
can enter its rolling features. This is sequential next-game evaluation, not
a forecast of an entire season from opening night.

## Opponent defensive rating: additional engineering required

The NBA defines team defensive rating in terms of points allowed per 100
possessions ([NBA statistics explainer](https://jr.nba.com/basictraditional-stats-vs-advanced-stats/)).
Points allowed per game, steals, blocks, ESPN `NBARating`, and scoring efficiency
are not interchangeable with this metric.

The sampled site feed had three statistical categories and no defensive rating.
The core feed had 109 stat entries across its three categories, including pace
and possession estimates, but no observed defensive rating. Some core fields
were populated with zero despite a full season of play (`minutes`, for example);
field presence alone does not prove usability. ESPN's
[Hollinger team page](https://www.espn.com/nba/hollinger/teamstats) was blocked
by a browser-verification challenge during inspection and is not a verified API
source for this assessment.

Recommended ESPN-only estimate, explicitly named `opponent_def_rating_est`:

```text
team_poss_est = FGA + 0.44 * FTA - OREB + total_turnovers
game_poss_est = (team_poss_est + other_team_poss_est) / 2
opponent_def_rating_est(t) =
    100 * SUM(points_allowed by target opponent before t)
        / SUM(game_poss_est for those same games before t)
```

This is a proposed box-score approximation, not a validated reproduction of
NBA's official metric. The 0.44 coefficient is a modeling assumption to validate.
Use one regular-season-to-date window, reset at the season boundary, and leave
the first game's rating missing or use an explicitly agreed prior-season prior.
For sparse early-season history, evaluate shrinkage against a league prior
computed before the same cutoff. Do not average individual game ratings when
the intended metric is a ratio of total points to total possessions.

The inspected summary supplies both teams' FGA, FTA, OREB and
`totalTurnovers`, with points from header competitor scores. Prefer
`totalTurnovers` to player turnover sums: team turnovers need not belong to an
individual. The example game gives possession estimates 100.92 and 102.12,
averaging 101.52; Golden State's single-game estimated rating would be
`100 * 124 / 101.52 ≈ 122.14`. This result must not enter that game's pregame
features, and one game is not a season rating.

Required processing: enumerate each team's eligible games, fetch/deduplicate
complete final box scores, store both team rows per game, then join the target
opponent's aggregate at the pregame cutoff. Summing the five sampled players'
stats cannot reconstruct team totals or defensive history.

If the teammate requires official NBA `DEF_RATING`, investigate an approved
official data extract separately. Its endpoint reliability, access, and historical
coverage were not verified here. Even official final-season values would leak
future outcomes when attached to earlier games.

## Additional candidate features

These are plausible candidates; this research does not claim measured accuracy
improvements. Compare additions against the same held-out dates and baseline.

| Candidate | Availability / inputs | Calculation and recommendation |
| --- | --- | --- |
| Last 5 FTA | Derived from game-log FT or summary `FT` | `fta_last5_avg`, shifted rolling mean; captures scoring opportunity at the line. Included in CSV. |
| Last 5 three-point attempts | Derived from game-log three-point field or summary `3PT` | `three_pa_last5_avg`, shifted rolling mean; captures shot mix and volume. Included. |
| Last 5 points variability | Derived from points | `pts_last5_std`, shifted population standard deviation (`ddof=0`); 0 for one prior game, NULL for none. Included; may help assess unstable roles but needs validation. |
| Season-to-date points average | Already implemented | `pts_season_avg`; retain as a stable baseline alongside recent form. Included. |
| Team/opponent pace | Direct season aggregate observed in core team stats; historical pregame feature needs derivation | `paceFactor` exists, but current/final season totals leak at earlier dates. Defer until complete team histories are stored. |
| Starting role and teammate availability | Summary entries expose `starter`; summary has injury information | Prior starting frequency could be derived after history collection. A final box-score starter flag or retrospectively updated injury report cannot establish what was known before tipoff. Pregame starter/injury snapshots require timestamped collection. Not included. |

## PostgreSQL and pipeline recommendations

The existing schema already stores the base inputs for the eight supported
features: `player_game_stats` player/game IDs, points, minutes, FGM/FGA, FG%,
FTM/FTA, 3PM/3PA, `is_home`, `opponent_team_id`, plus `games.game_date` and
home/away team IDs. No migration is required to experiment with these features.

`recent_minutes_avg` already represents the previous five games and is
recalculated in ingestion. Existing points features and their tests already
handle lagging and season resets. The modeling dataset loader currently exports
points/minutes/context but omits the shooting columns needed for new FGA/FG%
features. A production implementation must extend that export and the inference
history payload, and train a new versioned artifact with the same feature names,
order, types, units, missing-value rules, and rounding as inference.

For reliable future context, retain scheduled event identity, tipoff timestamp,
season/type, status, home/away team IDs and neutral-site status. A calendar date
alone cannot prove completion before the prediction cutoff or order multiple
same-day events. Persist source identity/mapping and retrieval timestamps for
auditability; upcoming events can change dates or opponents.

For defensive estimates, a proposed `team_game_stats` table needs unique
`(team_id, game_id)`, opponent ID, points for/against, FGA, FTA, OREB,
total turnovers, and the corresponding opponent counts (or a self-join to the
other team row). Join games for date/tipoff/season/status. Compute the rating
from prior completed games rather than storing one mutable current-season
number in `teams`. No such table or ingestion was added in this research task.

## Historical coverage and observed limitations

1. **All-Star contamination is confirmed.** Curry's 2024–25 regular-season
   category includes events `401752956` and `401752957`, with non-franchise
   team IDs `130580`, `130754`, and `130579`; metadata identifies All-Star
   games. Across the ten sampled player-season logs, ten player appearances
   involve exhibition teams. The CSV excludes them using the captured 30-team
   catalog. The existing `player_events` category filter alone does not exclude
   these entries; current full ingestion's unknown-team mapping should reject
   them, but a lightweight points-only consumer also needs this filter.
2. **Season metadata can conflict.** A team-statistics request for 2025 returned
   root `season.year = 2027`, `requestedSeason.year = 2025`, and 82-game
   historical totals. The historical schedule had the same root-season mismatch,
   while its events identified 2024–25. Validate requested season and event-level
   metadata; do not label historical data from the root current-season value.
3. **Coverage is sampled, not exhaustive.** Curry's 2019–20 log returned five
   regular-season appearances; this does not prove continuous multi-decade
   coverage or that an empty response means a player had no games. Ten complete
   requested player-season responses were captured for this CSV; there was no
   independent league-wide completeness audit or earliest-supported-year test.
4. **Active rosters are not a historical player catalog.** Retired players and
   past rosters need explicit verified IDs or a historical source. ESPN athlete,
   team and event IDs differ from internal NBA identities. The sample retains
   both team/player namespaces; production game ingestion may reuse an existing
   legacy game ID instead of the CSV's `espn:` ID.
5. **Minutes and percentages need consistent treatment.** The selected logs have
   numeric display minutes; the production summary parser supports `MM:SS` and
   rounds to integer minutes. Display precision cannot recover exact seconds.
   Missing values, zero-attempt games, and partial windows need the same policy
   in training and inference.
6. **Operational guarantees were not established.** No rate limit, historical
   retention guarantee, or schema stability guarantee was verified. Existing
   retrieval uses timeouts and status validation, but large backfills still need
   caching, bounded concurrency and explicit reporting of missing games. Use
   offline snapshots for repeatable experiments. Historical corrections can
   change a regenerated dataset.
7. **Historical retrieval is not point-in-time archiving.** Current corrected
   stats may differ from what was originally published. Final season aggregates,
   current injuries and current rosters cannot be backfilled as pregame facts.
8. **Model wiring needs a separate implementation pass.** The inspected backend
   service still describes a last-five baseline, while training code lists a
   five-feature random forest. `ml/predict_player.py` contains committed merge
   conflict markers. These pre-existing conditions were recorded, not repaired;
   the CSV/rebuild/tests do not import that prediction module. Agree on the
   actual inference path before adding model features.

## ML teammate handoff: CSV contract and usage

Deliver [points_training.csv](../data/sample/espn_feature_research/points_training.csv)
with this assessment and its snapshot. It has **575 real player-game rows** from
October 22, 2024 through April 12, 2026. The five-player sample is deliberately
small and biased toward prominent players; it is an experiment input, not a
production training population or an accuracy benchmark.

| Player | 2024–25 (`train`) | 2025–26 (`test`) |
| --- | ---: | ---: |
| Stephen Curry | 70 | 43 |
| LeBron James | 70 | 60 |
| Jayson Tatum | 72 | 16 |
| Giannis Antetokounmpo | 68 | 36 |
| Anthony Edwards | 79 | 61 |
| Total | 359 | 216 |

The CSV retains cold-start rows. Each player's first captured appearance has
blank rolling features; each season's first appearance has blank
`pts_season_avg`. Filtering to at least ten prior appearances and a present
season average leaves 309 train and 211 test rows. Choose a consistent filter
or fit imputation only on training data. Do not tune against the final test
season; use date-based validation within the training season.

| Column group | Meaning / handling |
| --- | --- |
| `points` | Target outcome for the row's game. Never an input feature. |
| `player_id`, `team_id`, `opponent_team_id` | Existing internal NBA IDs; use for joins/grouping, not automatic numeric predictors. |
| `espn_player_id`, `espn_team_id`, `espn_opponent_team_id`, `game_id` | Source identities; `game_id` is `espn:{eventId}`. Legacy database game reconciliation is still required. |
| `player_name`, `game_date`, `season_end_year`, `season` | Metadata; `season` is start year from the existing helper. The authoritative captured season is `season_end_year`. |
| `actual_*` | The target game's minutes and shooting outcomes, provided for auditing/rebuilding. **Never include these in model inputs.** |
| `prior_games_count` | Number of earlier appearances in the captured two-season history; use to select sufficient-history rows. |
| `split` | Chronological train/test assignment, not a predictor. |
| The 12 allowlisted feature columns below | Prior performance/context; all are numeric, percentages are fractions, and blanks mean unavailable. |

Minimal loading example, using the rebuild script's explicit feature allowlist:

```python
import pandas as pd
from scripts.build_espn_feature_sample import FEATURES

data = pd.read_csv("data/sample/espn_feature_research/points_training.csv")
eligible = data[(data.prior_games_count >= 10) & data.pts_season_avg.notna()]
train = eligible[eligible.split == "train"]
test = eligible[eligible.split == "test"]
X_train, y_train = train[FEATURES], train["points"]
X_test, y_test = test[FEATURES], test["points"]
```

`FEATURES` contains `pts_season_avg`, `pts_last5_avg`, `pts_last10_avg`,
`recent_minutes_avg`, `fga_last5_avg`, `fga_last10_avg`, `is_home`,
`days_since_last_game`, `fg_pct_last5_avg`, `fta_last5_avg`,
`three_pa_last5_avg`, and `pts_last5_std`. Opponent defensive rating is
intentionally absent; it was not populated with zeros or a different metric.

Rebuild and validate offline, from the repository root:

```sh
python -m scripts.build_espn_feature_sample
python -m pytest tests/test_espn_feature_sample.py tests/test_points_features.py -q
```

The snapshot contains reduced live game-log responses, full-response hashes,
URLs, capture time, and the verified team mapping. Endpoint excerpts are
separate research evidence, not production test fixtures. Tests verify the
committed CSV matches its snapshot, player isolation, rolling windows, current
outcome exclusion, season behavior, chronological holdout, exhibition filtering,
and rejection of invalid shooting counts. They make no live API or database calls.

### Coordination status and proposed message

This document and the CSV are the prepared repository handoff. No teammate
acknowledgement or external delivery has been recorded. The teammate's destination
was not supplied; sharing/coordination remains pending.

> ESPN supports eight requested features; opponent defensive rating needs a
> complete team-history estimate or a separately verified official source.
> `data/sample/espn_feature_research/points_training.csv` has 575 real appearances,
> 12 candidate inputs, and a chronological split. Please use the explicit
> `FEATURES` allowlist: `points` is the label and `actual_*` columns are target-game
> outcomes. Definitions and caveats are in `docs/espn_feature_availability.md`.
> Before model integration, let's agree on short-history handling, arithmetic
> versus pooled FG%, whether rolling windows cross seasons, and the inference
> request's target event/date/opponent. Please compare new features against the
> existing points baseline on identical dates and report held-out MAE.
