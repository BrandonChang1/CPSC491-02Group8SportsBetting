"""Leakage-safe player-game features for the points model.

Every feature for a game uses only games played before it: rows are sorted by
date, shifted by one game, then rolled. Same-game box-score values are outcomes
and only appear in columns prefixed ``target_``.

Inputs are the tables parsed from ESPN box scores by scripts/build_dataset.py:
    players     one row per player who played in a game (didNotPlay excluded)
    team_games  one row per team per game (team box score)
    bios        one row per ESPN athlete (birth date, height, debut year, position)
    id_map      espn_player_id -> player_id (app convention)
"""

import numpy as np
import pandas as pd

EWM_SPAN = 10
ROTATION_MIN_AVG = 15
ROTATION_MIN_GAMES = 5
LOW_MINUTES = 10
MIN_HISTORY = 5
HOME_COURT_POINTS = 2.0
DAYS_REST_CAP = 10
TEAM_WINDOW = 10
SPLITS = {2021: "train", 2022: "train", 2023: "train", 2024: "val", 2025: "test"}
POSITION_GROUPS = {
    "PG": "G", "SG": "G", "G": "G", "G-F": "G",
    "SF": "F", "PF": "F", "F": "F", "F-G": "F", "F-C": "F",
    "C": "C", "C-F": "C",
}

# Same-game box score value -> target column name.
TARGETS = {
    "points": "target_pts",
    "minutes": "target_min",
    "field_goals_made": "target_fgm",
    "field_goals_attempted": "target_fga",
    "three_pointers_made": "target_fg3m",
    "three_pointers_attempted": "target_fg3a",
    "free_throws_made": "target_ftm",
    "free_throws_attempted": "target_fta",
    "offensive_rebounds": "target_oreb",
    "defensive_rebounds": "target_dreb",
    "rebounds": "target_reb",
    "assists": "target_ast",
    "steals": "target_stl",
    "blocks": "target_blk",
    "turnovers": "target_tov",
    "personal_fouls": "target_pf",
    "plus_minus": "target_plus_minus",
    "starter": "target_starter",
    "usg_pct": "target_usg_pct",
    "ts_pct": "target_ts_pct",
    "team_points": "target_team_pts",
    "opponent_points": "target_opp_pts",
}

ESPN_BOX = "ESPN box score (site/v2 summary)"
ESPN_TEAM_BOX = "ESPN team box score (site/v2 summary)"
ESPN_BIO = "ESPN core athlete (sports.core.api …/athletes/{id})"
DERIVED = "Derived from ESPN box scores"

# column -> (group, definition, source)
FEATURE_DOCS = {
    # identity
    "player_id": ("Identity", "App player id: NBA id when verified/name-matched, else 9,000,000,000 + ESPN id (see player_id_map.csv)", "data/collection/espn_player_ids.json, legacy_nba_ids.json"),
    "espn_player_id": ("Identity", "ESPN athlete id", ESPN_BOX),
    "player_name": ("Identity", "ESPN display name", ESPN_BOX),
    "game_id": ("Identity", "espn:<event id>", ESPN_BOX),
    "game_date": ("Identity", "Game date in US/Eastern (YYYY-MM-DD)", ESPN_BOX),
    "season": ("Identity", "Season start year (2024 = 2024-25)", "ESPN schedule"),
    "split": ("Identity", "train = 2021-22..2023-24, val = 2024-25, test = 2025-26", "Derived"),
    "team_id": ("Identity", "NBA team id of the player's team", ESPN_BOX),
    "team_abbreviation": ("Identity", "Player's team abbreviation", ESPN_BOX),
    "opponent_team_id": ("Identity", "NBA team id of the opponent", ESPN_BOX),
    "opponent_abbreviation": ("Identity", "Opponent abbreviation", ESPN_BOX),
    "matchup": ("Identity", "'TEAM vs. OPP' at home, 'TEAM @ OPP' away", ESPN_BOX),
    # targets
    "target_pts": ("Target (same game, NOT a feature)", "Points scored in this game", ESPN_BOX),
    "target_min": ("Target (same game, NOT a feature)", "Minutes played in this game", ESPN_BOX),
    "target_fgm": ("Target (same game, NOT a feature)", "Field goals made", ESPN_BOX),
    "target_fga": ("Target (same game, NOT a feature)", "Field goals attempted", ESPN_BOX),
    "target_fg3m": ("Target (same game, NOT a feature)", "Threes made", ESPN_BOX),
    "target_fg3a": ("Target (same game, NOT a feature)", "Threes attempted", ESPN_BOX),
    "target_ftm": ("Target (same game, NOT a feature)", "Free throws made", ESPN_BOX),
    "target_fta": ("Target (same game, NOT a feature)", "Free throws attempted", ESPN_BOX),
    "target_oreb": ("Target (same game, NOT a feature)", "Offensive rebounds", ESPN_BOX),
    "target_dreb": ("Target (same game, NOT a feature)", "Defensive rebounds", ESPN_BOX),
    "target_reb": ("Target (same game, NOT a feature)", "Rebounds", ESPN_BOX),
    "target_ast": ("Target (same game, NOT a feature)", "Assists", ESPN_BOX),
    "target_stl": ("Target (same game, NOT a feature)", "Steals", ESPN_BOX),
    "target_blk": ("Target (same game, NOT a feature)", "Blocks", ESPN_BOX),
    "target_tov": ("Target (same game, NOT a feature)", "Turnovers", ESPN_BOX),
    "target_pf": ("Target (same game, NOT a feature)", "Personal fouls", ESPN_BOX),
    "target_plus_minus": ("Target (same game, NOT a feature)", "Plus/minus", ESPN_BOX),
    "target_starter": ("Target (same game, NOT a feature)", "Started this game (lineups are only official ~30 min before tip)", ESPN_BOX),
    "target_usg_pct": ("Target (same game, NOT a feature)", "Usage % this game: 100·(FGA+0.44·FTA+TOV)·(TmMIN/5) / (MIN·(TmFGA+0.44·TmFTA+TmTOV)); NaN if MIN = 0", DERIVED),
    "target_ts_pct": ("Target (same game, NOT a feature)", "True shooting this game: PTS / (2·(FGA+0.44·FTA)); NaN with no attempts", DERIVED),
    "target_team_pts": ("Target (same game, NOT a feature)", "Player's team final score", ESPN_TEAM_BOX),
    "target_opp_pts": ("Target (same game, NOT a feature)", "Opponent final score", ESPN_TEAM_BOX),
    # minutes / role
    "min_ewm": ("Minutes & role", f"EWM (span {EWM_SPAN}) of minutes over prior games, carried across seasons", DERIVED),
    "min_last1": ("Minutes & role", "Minutes in the player's previous game", DERIVED),
    "min_season_avg": ("Minutes & role", "Mean minutes over prior games this season", DERIVED),
    "min_std_last10": ("Minutes & role", "Std. dev. of minutes over the prior 10 games (needs 2)", DERIVED),
    "team_min_share_ewm": ("Minutes & role", "EWM of minutes / team player-minutes (240 + 25 per OT) over prior games", DERIVED),
    "fouls_per_min_ewm": ("Minutes & role", "EWM(personal fouls) / EWM(minutes) over prior games", DERIVED),
    "starter_rate_last10": ("Minutes & role", "Share of the prior 10 games the player started", DERIVED),
    # scoring form
    "pts_ewm": ("Scoring form", f"EWM (span {EWM_SPAN}) of points over prior games, across seasons", DERIVED),
    "fga_ewm": ("Scoring form", "EWM of FGA over prior games", DERIVED),
    "fg3a_ewm": ("Scoring form", "EWM of 3PA over prior games", DERIVED),
    "fta_ewm": ("Scoring form", "EWM of FTA over prior games", DERIVED),
    "usg_pct_ewm": ("Scoring form", "EWM of per-game usage % over prior games (games with 0 min skipped)", DERIVED),
    "ts_pct_ewm": ("Scoring form", "pts_ewm / (2·(fga_ewm + 0.44·fta_ewm))", DERIVED),
    "pts_season_avg": ("Scoring form", "Mean points over prior games this season (resets each season)", DERIVED),
    "fga_season_avg": ("Scoring form", "Mean FGA over prior games this season", DERIVED),
    "fg3a_season_avg": ("Scoring form", "Mean 3PA over prior games this season", DERIVED),
    "fta_season_avg": ("Scoring form", "Mean FTA over prior games this season", DERIVED),
    "usg_pct_season_avg": ("Scoring form", "Mean per-game usage % over prior games this season (0-min games skipped)", DERIVED),
    "ts_pct_season_avg": ("Scoring form", "Season-to-date ΣPTS / (2·Σ(FGA+0.44·FTA)) over prior games", DERIVED),
    "pts_last5_avg": ("Scoring form", "Mean points over the prior 5 games (across seasons, min 1)", DERIVED),
    "pts_last10_avg": ("Scoring form", "Mean points over the prior 10 games (across seasons, min 1)", DERIVED),
    "pts_per_min_ewm": ("Scoring form", "pts_ewm / min_ewm", DERIVED),
    "pts_std_last10": ("Scoring form", "Std. dev. of points over the prior 10 games (needs 2)", DERIVED),
    "pts_last5_minus_season": ("Scoring form", "pts_last5_avg − pts_season_avg", DERIVED),
    "prev_season_pts_avg": ("Scoring form", "Mean points over the whole previous season", DERIVED),
    "prev_season_min_avg": ("Scoring form", "Mean minutes over the whole previous season", DERIVED),
    "games_played_season": ("Scoring form", "Games played earlier this season", DERIVED),
    "prior_games": ("Scoring form", "Games played earlier in the dataset (all seasons)", DERIVED),
    # teammates
    "rotation_size": ("Teammate availability", f"Rotation teammates for this team-game: on this team as of their latest prior game, {ROTATION_MIN_GAMES}+ prior games and {ROTATION_MIN_AVG}+ prior avg min this season. NaN if none yet", DERIVED),
    "rotation_out": ("Teammate availability", "Rotation teammates with no played row in this game (DNP or absent)", DERIVED),
    "missing_ppg": ("Teammate availability", "Sum of prior season-avg points of out rotation teammates", DERIVED),
    "missing_min": ("Teammate availability", "Sum of prior season-avg minutes of out rotation teammates", DERIVED),
    "top3_scorers_out": ("Teammate availability", "Out teammates among the team's top 3 rotation scorers by prior season PPG", DERIVED),
    "games_missed_last14": ("Teammate availability", "Team games in the prior 14 days minus the player's own games in that window (min 0)", DERIVED),
    "days_since_last_game": ("Teammate availability", "Days since the player's previous game (any season)", DERIVED),
    # schedule
    "is_home": ("Schedule", "Player's team is at home", ESPN_BOX),
    "days_rest": ("Schedule", f"Days since the team's previous game, capped at {DAYS_REST_CAP}", DERIVED),
    "is_back_to_back": ("Schedule", "Team played the previous day", DERIVED),
    "games_last7": ("Schedule", "Team games in the prior 7 days", DERIVED),
    "opp_days_rest": ("Schedule", f"Opponent's days since previous game, capped at {DAYS_REST_CAP}", DERIVED),
    "opp_is_back_to_back": ("Schedule", "Opponent played the previous day", DERIVED),
    # team / opponent
    "team_off_rating": ("Team & opponent", f"Team offensive rating (100·PTS/poss) over its prior {TEAM_WINDOW} games", DERIVED),
    "team_def_rating": ("Team & opponent", f"Team defensive rating over its prior {TEAM_WINDOW} games", DERIVED),
    "team_pace": ("Team & opponent", f"Team pace (possessions per 48) over its prior {TEAM_WINDOW} games", DERIVED),
    "opp_off_rating": ("Team & opponent", f"Opponent offensive rating over its prior {TEAM_WINDOW} games", DERIVED),
    "opp_def_rating": ("Team & opponent", f"Opponent defensive rating (100·pts allowed/poss) over its prior {TEAM_WINDOW} games", DERIVED),
    "opp_pace": ("Team & opponent", f"Opponent pace over its prior {TEAM_WINDOW} games", DERIVED),
    "opp_pts_allowed": ("Team & opponent", f"Opponent points allowed per game, prior {TEAM_WINDOW} games", DERIVED),
    "opp_fg3a_allowed": ("Team & opponent", f"Opponent 3PA allowed per game, prior {TEAM_WINDOW} games", DERIVED),
    "opp_fta_allowed": ("Team & opponent", f"Opponent FTA allowed per game, prior {TEAM_WINDOW} games", DERIVED),
    "opp_pts_allowed_pos": ("Team & opponent", f"Points the opponent allowed to the player's position group per game, prior {TEAM_WINDOW} games", DERIVED),
    "opp_pts_allowed_pos_rel": ("Team & opponent", "opp_pts_allowed_pos / league mean points allowed to that group per team-game this season before this date", DERIVED),
    # environment
    "league_off_rating": ("Game environment", "League ΣPTS/Σposs ×100 over this season's games before this date (prior season's value on opening night)", DERIVED),
    "exp_pace": ("Game environment", "(team_pace + opp_pace) / 2", DERIVED),
    "exp_team_pts": ("Game environment", "team_off_rating × opp_def_rating / league_off_rating × exp_pace / 100", DERIVED),
    "exp_margin": ("Game environment", f"(team net rating − opp net rating) × exp_pace / 100 ± {HOME_COURT_POINTS} home-court points", DERIVED),
    "exp_margin_abs": ("Game environment", "|exp_margin| (blowout risk)", DERIVED),
    # static
    "position": ("Player", "ESPN listed position (bio), else most common box-score position", ESPN_BIO),
    "pos_group": ("Player", "G / F / C from the player's most common box-score position", ESPN_BOX),
    "height_in": ("Player", "Height in inches", ESPN_BIO),
    "age_at_game": ("Player", "Age in years on game date", ESPN_BIO),
    "experience_years": ("Player", "season − ESPN debutYear (0 = rookie)", ESPN_BIO),
    # flags
    "low_minutes_prior": ("Flags", f"min_ewm < {LOW_MINUTES}", DERIVED),
    "insufficient_history": ("Flags", f"Fewer than {MIN_HISTORY} prior games", DERIVED),
}


# ----------------------------------------------------------------- prior helpers


def _shifted(df, col, by):
    return df.groupby(by, sort=False)[col].shift(1)


def prior_ewm(df, col, by="player_id"):
    shifted = _shifted(df, col, by)
    keys = [df[k] for k in ([by] if isinstance(by, str) else by)]
    return shifted.groupby(keys, sort=False).transform(
        lambda s: s.ewm(span=EWM_SPAN, min_periods=1, ignore_na=True).mean()
    )


def prior_rolling(df, col, window, stat="mean", by="player_id", min_periods=1):
    shifted = _shifted(df, col, by)
    keys = [df[k] for k in ([by] if isinstance(by, str) else by)]
    return shifted.groupby(keys, sort=False).transform(
        lambda s: getattr(s.rolling(window, min_periods=min_periods), stat)()
    )


def prior_expanding(df, col, by, stat="mean"):
    shifted = _shifted(df, col, by)
    keys = [df[k] for k in by]
    return shifted.groupby(keys, sort=False).transform(
        lambda s: getattr(s.expanding(min_periods=1), stat)()
    )


def prior_window_count(dates, keys, days):
    """For each row: rows with the same key dated in [date - days, date)."""

    out = pd.Series(np.nan, index=dates.index)
    span = np.timedelta64(days, "D")
    for index in dates.groupby(keys, sort=False).groups.values():
        ordered = dates.loc[index].sort_values()
        values = ordered.to_numpy()
        lower = np.searchsorted(values, values - span, side="left")
        upper = np.searchsorted(values, values, side="left")
        out.loc[ordered.index] = upper - lower
    return out


def _safe_div(numerator, denominator):
    denominator = denominator.where(denominator != 0)
    return numerator / denominator


# ------------------------------------------------------------------- team table


def team_game_table(team_games):
    """Per team-game: possessions, ratings, pace, allowed stats and schedule, plus prior rolls."""

    teams = team_games.copy()
    teams["game_date"] = pd.to_datetime(teams["game_date"])
    teams["own_poss"] = (
        teams["field_goals_attempted"]
        - teams["offensive_rebounds"]
        + teams["turnovers"]
        + 0.44 * teams["free_throws_attempted"]
    )
    other = teams[
        ["game_id", "team_id", "points", "own_poss", "three_pointers_attempted", "free_throws_attempted"]
    ].rename(
        columns={
            "team_id": "opponent_team_id",
            "points": "opponent_points",
            "own_poss": "opp_own_poss",
            "three_pointers_attempted": "fg3a_allowed",
            "free_throws_attempted": "fta_allowed",
        }
    )
    teams = teams.merge(other, on="game_id")
    teams = teams[teams["team_id"] != teams["opponent_team_id"]]
    if teams.duplicated(["team_id", "game_id"]).any():
        raise ValueError("Duplicate team-game rows")

    teams["poss"] = (teams["own_poss"] + teams["opp_own_poss"]) / 2
    teams["team_player_minutes"] = 240 + 25 * teams["overtimes"]
    game_minutes = 48 + 5 * teams["overtimes"]
    teams["pace_game"] = 48 * teams["poss"] / game_minutes
    teams["off_rating_game"] = 100 * teams["points"] / teams["poss"]
    teams["def_rating_game"] = 100 * teams["opponent_points"] / teams["poss"]
    teams["net_rating_game"] = teams["off_rating_game"] - teams["def_rating_game"]

    teams = teams.sort_values(["team_id", "game_date", "game_id"]).reset_index(drop=True)
    for source, name in {
        "off_rating_game": "off_rating",
        "def_rating_game": "def_rating",
        "net_rating_game": "net_rating",
        "pace_game": "pace",
        "opponent_points": "pts_allowed",
        "fg3a_allowed": "fg3a_allowed_roll",
        "fta_allowed": "fta_allowed_roll",
    }.items():
        teams[name] = prior_rolling(teams, source, TEAM_WINDOW, by="team_id")

    previous = teams.groupby("team_id")["game_date"].shift(1)
    teams["days_rest"] = (teams["game_date"] - previous).dt.days.clip(upper=DAYS_REST_CAP)
    teams["is_back_to_back"] = teams["days_rest"] == 1
    teams["games_last7"] = prior_window_count(teams["game_date"], teams["team_id"], 7)
    teams["games_last14"] = prior_window_count(teams["game_date"], teams["team_id"], 14)

    # League offensive rating from games on earlier dates this season.
    daily = (
        teams.groupby(["season", "game_date"])[["points", "poss"]].sum().reset_index()
    )
    by_season = daily.groupby("season")
    daily["league_off_rating"] = 100 * by_season["points"].transform(
        lambda s: s.cumsum().shift(1)
    ) / by_season["poss"].transform(lambda s: s.cumsum().shift(1))
    season_final = (100 * by_season["points"].sum() / by_season["poss"].sum()).to_dict()
    opener = daily["league_off_rating"].isna()
    daily.loc[opener, "league_off_rating"] = daily.loc[opener, "season"].map(
        lambda s: season_final.get(s - 1, np.nan)
    )
    teams = teams.merge(daily[["season", "game_date", "league_off_rating"]], on=["season", "game_date"])
    return teams


def position_allowed_table(players, teams):
    """Per defending team-game: prior points allowed to G/F/C, absolute and vs league."""

    scored = (
        players.groupby(["game_id", "opponent_team_id", "pos_group"])["points"]
        .sum()
        .unstack("pos_group")
        .reindex(columns=["G", "F", "C"])
        .fillna(0.0)
        .reset_index()
        .rename(columns={"opponent_team_id": "team_id"})
    )
    table = teams[["team_id", "game_id", "game_date", "season"]].merge(
        scored, on=["team_id", "game_id"], how="left"
    )
    table[["G", "F", "C"]] = table[["G", "F", "C"]].fillna(0.0)
    table = table.sort_values(["team_id", "game_date", "game_id"]).reset_index(drop=True)

    daily = table.groupby(["season", "game_date"]).agg(
        G=("G", "sum"), F=("F", "sum"), C=("C", "sum"), n=("game_id", "size")
    ).reset_index()
    out = table[["team_id", "game_id"]].copy()
    for group in ("G", "F", "C"):
        out[f"allowed_{group}"] = prior_rolling(table, group, TEAM_WINDOW, by="team_id")
        cum = daily.groupby("season")[group].transform(lambda s: s.cumsum().shift(1))
        count = daily.groupby("season")["n"].transform(lambda s: s.cumsum().shift(1))
        daily[f"league_{group}"] = cum / count
    table = table.merge(
        daily[["season", "game_date", "league_G", "league_F", "league_C"]],
        on=["season", "game_date"],
    )
    out = out.merge(table[["team_id", "game_id", "league_G", "league_F", "league_C"]], on=["team_id", "game_id"])
    return out


# ------------------------------------------------------------------- teammates


def teammate_availability(df, teams):
    """missing_ppg / missing_min / top3_scorers_out / rotation counts per team-game."""

    state = df[["player_id", "game_date", "season", "team_id", "minutes", "points"]].copy()
    by_season = state.groupby(["player_id", "season"], sort=False)
    state["post_gp"] = by_season.cumcount() + 1
    state["post_min_avg"] = by_season["minutes"].transform(lambda s: s.expanding().mean())
    state["post_pts_avg"] = by_season["points"].transform(lambda s: s.expanding().mean())
    state = state.rename(columns={"season": "state_season", "team_id": "state_team"})[
        ["player_id", "game_date", "state_season", "state_team", "post_gp", "post_min_avg", "post_pts_avg"]
    ].sort_values("game_date")

    candidates = df[["team_id", "season", "player_id"]].drop_duplicates()
    grid = teams[["team_id", "season", "game_id", "game_date"]].merge(
        candidates, on=["team_id", "season"]
    ).sort_values("game_date")
    grid = pd.merge_asof(
        grid, state, on="game_date", by="player_id", allow_exact_matches=False
    )
    rotation = grid[
        (grid["state_team"] == grid["team_id"])
        & (grid["state_season"] == grid["season"])
        & (grid["post_gp"] >= ROTATION_MIN_GAMES)
        & (grid["post_min_avg"] >= ROTATION_MIN_AVG)
    ].copy()

    played = df[["player_id", "game_id"]].assign(played=True)
    rotation = rotation.merge(played, on=["player_id", "game_id"], how="left")
    rotation["out"] = rotation["played"].isna()
    rotation["scorer_rank"] = rotation.groupby(["team_id", "game_id"])["post_pts_avg"].rank(
        ascending=False, method="first"
    )
    rotation["out_ppg"] = rotation["post_pts_avg"].where(rotation["out"], 0.0)
    rotation["out_min"] = rotation["post_min_avg"].where(rotation["out"], 0.0)
    rotation["top3_out"] = rotation["out"] & (rotation["scorer_rank"] <= 3)

    return (
        rotation.groupby(["team_id", "game_id"])
        .agg(
            rotation_size=("player_id", "size"),
            rotation_out=("out", "sum"),
            missing_ppg=("out_ppg", "sum"),
            missing_min=("out_min", "sum"),
            top3_scorers_out=("top3_out", "sum"),
        )
        .reset_index()
    )


# ------------------------------------------------------------------------ build


def _pos_group(value):
    if not isinstance(value, str) or not value:
        return None
    return POSITION_GROUPS.get(value, {"P": "G", "S": "G"}.get(value[0], value[0] if value[0] in "GFC" else None))


def build_features(players, team_games, bios, id_map):
    """Return the modeling table: identity, target_* outcomes, prior-only features, flags."""

    teams = team_game_table(team_games)

    df = players.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.merge(id_map[["espn_player_id", "player_id"]], on="espn_player_id", how="left")
    if df["player_id"].isna().any():
        raise ValueError("Every ESPN athlete must be in id_map")
    df["player_id"] = df["player_id"].astype("int64")

    team_cols = teams[
        [
            "team_id", "game_id", "points", "opponent_points", "field_goals_attempted",
            "free_throws_attempted", "turnovers", "team_player_minutes",
        ]
    ].rename(
        columns={
            "points": "team_points",
            "opponent_points": "opponent_points",
            "field_goals_attempted": "team_fga",
            "free_throws_attempted": "team_fta",
            "turnovers": "team_tov",
        }
    )
    df = df.merge(team_cols, on=["team_id", "game_id"], how="left", validate="many_to_one")

    df["usg_pct"] = _safe_div(
        100
        * (df["field_goals_attempted"] + 0.44 * df["free_throws_attempted"] + df["turnovers"])
        * (df["team_player_minutes"] / 5),
        df["minutes"] * (df["team_fga"] + 0.44 * df["team_fta"] + df["team_tov"]),
    )
    df["ts_shots"] = 2 * (df["field_goals_attempted"] + 0.44 * df["free_throws_attempted"])
    df["ts_pct"] = _safe_div(df["points"], df["ts_shots"])
    df["min_share"] = df["minutes"] / df["team_player_minutes"]

    # Static player attributes.
    modal = (
        df.groupby("espn_player_id")["box_position"]
        .agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None)
        .rename("modal_position")
    )
    df = df.merge(modal, on="espn_player_id", how="left")
    df = df.merge(bios, on="espn_player_id", how="left")
    df["position"] = df["bio_position"].fillna(df["modal_position"])
    df["pos_group"] = df["modal_position"].map(_pos_group).fillna(df["bio_position"].map(_pos_group))
    dob = pd.to_datetime(df["date_of_birth"], utc=True, errors="coerce").dt.tz_localize(None)
    df["age_at_game"] = (df["game_date"] - dob).dt.days / 365.25
    df["experience_years"] = (df["season"] - pd.to_numeric(df["debut_year"], errors="coerce")).clip(lower=0)

    df = df.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)
    if df.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Duplicate (player_id, game_id) rows")
    by_season = ["player_id", "season"]

    # Minutes and role.
    df["min_ewm"] = prior_ewm(df, "minutes")
    df["min_last1"] = _shifted(df, "minutes", "player_id")
    df["min_season_avg"] = prior_expanding(df, "minutes", by_season)
    df["min_std_last10"] = prior_rolling(df, "minutes", 10, "std", min_periods=2)
    df["team_min_share_ewm"] = prior_ewm(df, "min_share")
    df["fouls_per_min_ewm"] = _safe_div(prior_ewm(df, "personal_fouls"), df["min_ewm"])
    df["started"] = df["starter"].astype(float)
    df["starter_rate_last10"] = prior_rolling(df, "started", 10)

    # Scoring form.
    for source, name in {
        "points": "pts",
        "field_goals_attempted": "fga",
        "three_pointers_attempted": "fg3a",
        "free_throws_attempted": "fta",
        "usg_pct": "usg_pct",
    }.items():
        df[f"{name}_ewm"] = prior_ewm(df, source)
        df[f"{name}_season_avg"] = prior_expanding(df, source, by_season)
    df["ts_pct_ewm"] = _safe_div(df["pts_ewm"], 2 * (df["fga_ewm"] + 0.44 * df["fta_ewm"]))
    df["ts_pct_season_avg"] = _safe_div(
        prior_expanding(df, "points", by_season, "sum"),
        prior_expanding(df, "ts_shots", by_season, "sum"),
    )
    df["pts_last5_avg"] = prior_rolling(df, "points", 5)
    df["pts_last10_avg"] = prior_rolling(df, "points", 10)
    df["pts_per_min_ewm"] = _safe_div(df["pts_ewm"], df["min_ewm"])
    df["pts_std_last10"] = prior_rolling(df, "points", 10, "std", min_periods=2)
    df["pts_last5_minus_season"] = df["pts_last5_avg"] - df["pts_season_avg"]

    season_means = (
        df.groupby(by_season)[["points", "minutes"]].mean().reset_index()
        .rename(columns={"points": "prev_season_pts_avg", "minutes": "prev_season_min_avg"})
    )
    season_means["season"] += 1
    df = df.merge(season_means, on=by_season, how="left")

    df["games_played_season"] = df.groupby(by_season).cumcount()
    df["prior_games"] = df.groupby("player_id").cumcount()
    previous_date = df.groupby("player_id")["game_date"].shift(1)
    df["days_since_last_game"] = (df["game_date"] - previous_date).dt.days

    # Teammate availability.
    df = df.merge(teammate_availability(df, teams), on=["team_id", "game_id"], how="left")
    own_last14 = prior_window_count(df["game_date"], df["player_id"], 14)
    team_last14 = df[["team_id", "game_id"]].merge(
        teams[["team_id", "game_id", "games_last14"]], on=["team_id", "game_id"], how="left"
    )["games_last14"]
    df["games_missed_last14"] = (team_last14.to_numpy() - own_last14).clip(lower=0)

    # Schedule, team and opponent context.
    team_context = teams[
        [
            "team_id", "game_id", "days_rest", "is_back_to_back", "games_last7",
            "off_rating", "def_rating", "net_rating", "pace", "league_off_rating",
        ]
    ].rename(
        columns={
            "off_rating": "team_off_rating",
            "def_rating": "team_def_rating",
            "net_rating": "team_net_rating",
            "pace": "team_pace",
        }
    )
    opponent_context = teams[
        [
            "team_id", "game_id", "days_rest", "is_back_to_back", "off_rating",
            "def_rating", "net_rating", "pace", "pts_allowed", "fg3a_allowed_roll",
            "fta_allowed_roll",
        ]
    ].rename(
        columns={
            "team_id": "opponent_team_id",
            "days_rest": "opp_days_rest",
            "is_back_to_back": "opp_is_back_to_back",
            "off_rating": "opp_off_rating",
            "def_rating": "opp_def_rating",
            "net_rating": "opp_net_rating",
            "pace": "opp_pace",
            "pts_allowed": "opp_pts_allowed",
            "fg3a_allowed_roll": "opp_fg3a_allowed",
            "fta_allowed_roll": "opp_fta_allowed",
        }
    )
    df = df.merge(team_context, on=["team_id", "game_id"], how="left", validate="many_to_one")
    df = df.merge(opponent_context, on=["opponent_team_id", "game_id"], how="left", validate="many_to_one")

    allowed = position_allowed_table(df, teams).rename(columns={"team_id": "opponent_team_id"})
    df = df.merge(allowed, on=["opponent_team_id", "game_id"], how="left", validate="many_to_one")
    df["opp_pts_allowed_pos"] = np.nan
    df["opp_pts_allowed_pos_rel"] = np.nan
    for group in ("G", "F", "C"):
        mask = df["pos_group"] == group
        df.loc[mask, "opp_pts_allowed_pos"] = df.loc[mask, f"allowed_{group}"]
        df.loc[mask, "opp_pts_allowed_pos_rel"] = _safe_div(
            df.loc[mask, f"allowed_{group}"], df.loc[mask, f"league_{group}"]
        )

    df["exp_pace"] = (df["team_pace"] + df["opp_pace"]) / 2
    df["exp_team_pts"] = (
        df["team_off_rating"] * df["opp_def_rating"] / df["league_off_rating"] * df["exp_pace"] / 100
    )
    home_edge = np.where(df["is_home"], HOME_COURT_POINTS, -HOME_COURT_POINTS)
    df["exp_margin"] = (df["team_net_rating"] - df["opp_net_rating"]) * df["exp_pace"] / 100 + home_edge
    df["exp_margin_abs"] = df["exp_margin"].abs()

    # Flags, split, presentation.
    df["low_minutes_prior"] = df["min_ewm"] < LOW_MINUTES
    df["insufficient_history"] = df["prior_games"] < MIN_HISTORY
    df["split"] = df["season"].map(SPLITS)
    df["matchup"] = df["team_abbreviation"] + np.where(df["is_home"], " vs. ", " @ ") + df["opponent_abbreviation"]
    df = df.rename(columns=TARGETS)
    df["game_date"] = df["game_date"].dt.strftime("%Y-%m-%d")

    columns = list(FEATURE_DOCS)
    df = df[columns].sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
    floats = df.select_dtypes("float").columns
    df[floats] = df[floats].round(4)
    return df


# ------------------------------------------------------------- checks & report


def feature_columns(columns):
    identity = {c for c, (group, _, _) in FEATURE_DOCS.items() if group == "Identity"}
    return [c for c in columns if c not in identity and not c.startswith("target_")]


def validate(df, expected_rows_per_season):
    if df.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Duplicate (player_id, game_id) rows")
    raw_names = set(TARGETS)
    leaked = [c for c in feature_columns(df.columns) if c in raw_names]
    if leaked:
        raise ValueError(f"Same-game stats outside target_ columns: {leaked}")
    low, high = expected_rows_per_season
    counts = df.groupby("season").size()
    outside = counts[(counts < low) | (counts > high)]
    for season, count in outside.items():
        print(f"WARNING: season {season} has {count} rows (expected {low:,}-{high:,})")
    return counts


def report(df, id_map):
    lines = ["", "Rows per season:", df.groupby("season").size().to_string()]
    lines += ["", "Rows per split:", df["split"].value_counts().reindex(["train", "val", "test"]).to_string()]
    test = df[df["split"] == "test"]
    lines.append("")
    for column in ("pts_ewm", "pts_season_avg", "pts_last10_avg"):
        usable = test[test[column].notna()]
        mae = (usable[column] - usable["target_pts"]).abs().mean()
        lines.append(
            f"Test MAE {column:>15} vs target_pts: {mae:.3f} ({len(usable):,}/{len(test):,} rows)"
        )
    nulls = (df.isna().mean() * 100).round(2)
    lines += ["", "Null % per column:", nulls[nulls > 0].sort_values(ascending=False).to_string(), "(all other columns 0%)"]
    unmatched = id_map[id_map["nba_player_id"].isna()]
    lines += ["", f"ID map: {id_map['match_method'].value_counts().to_dict()}"]
    if len(unmatched):
        lines.append(f"Unmatched ({len(unmatched)}):")
        lines.append(unmatched[["espn_player_id", "player_name", "match_method", "teams"]].to_string(index=False))
    return "\n".join(lines)


def features_markdown(df):
    lines = [
        "# NBA_player_stats.csv — column reference",
        "",
        (
            "One row per player per regular-season game they played (ESPN box score, "
            "`didNotPlay` excluded), seasons 2021-22 through 2025-26. Built by "
            "`scripts/build_dataset.py`; features by `data/processing/full_features.py`."
        ),
        "",
        (
            "**Leakage rule:** every feature uses only games before the row's game "
            "(sort by date, shift one game, roll). Same-game values are outcomes and only "
            "appear as `target_*`. Season-to-date features reset each season; EWM "
            f"(span {EWM_SPAN}) and last-N features carry across seasons. NaN means no history."
        ),
        "",
        f"Rows: {len(df):,}. Columns: {df.shape[1]}.",
    ]
    group = None
    for column in df.columns:
        column_group, definition, source = FEATURE_DOCS[column]
        if column_group != group:
            group = column_group
            lines += ["", f"## {group}", "", "| Column | Definition | Source | Null % |", "|---|---|---|---|"]
        null = df[column].isna().mean() * 100
        lines.append(f"| `{column}` | {definition} | {source} | {null:.1f} |")
    return "\n".join(lines) + "\n"
