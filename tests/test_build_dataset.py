"""Leakage and integrity tests for data/NBA_player_stats.csv and its builder."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.processing import full_features as ff
from scripts import build_dataset

FIXTURES = Path(__file__).with_name("fixtures")
REAL_CSV = build_dataset.OUTPUT_CSV
TEAMS = [1610612737, 1610612738, 1610612739, 1610612740]
STAR = "1000"  # first player of team 0


def make_league(seasons=(2023, 2024), games_per_season=14, skip=(), seed=7):
    """Synthetic ESPN-shaped tables: 4 teams, 8 players each, alternating pairings.

    skip: (espn_player_id, season, game_number) tuples that get no played row.
    """

    rng = np.random.default_rng(seed)
    players, team_games = [], []
    pairings = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
    for season in seasons:
        date = pd.Timestamp(f"{season}-10-20")
        for number in range(games_per_season):
            date += pd.Timedelta(days=1 + number % 2)
            for slot, (home, away) in enumerate(pairings[number % 3]):
                game_id = f"espn:{season}{number:03d}{slot}"
                for side, opponent, is_home in ((home, away, True), (away, home, False)):
                    team_points = 0
                    for k in range(8):
                        espn_id = str(1000 + side * 10 + k)
                        if (espn_id, season, number) in skip:
                            continue
                        minutes = float(max(0, 34 - 4 * k + rng.integers(-3, 4)))
                        fga = int(rng.integers(0, 20 - k))
                        fta = int(rng.integers(0, 6))
                        points = int(rng.integers(0, 2 * fga + fta + 1)) + (12 if espn_id == STAR else 0)
                        team_points += points
                        players.append(
                            {
                                "espn_player_id": espn_id, "player_name": f"Player {espn_id}",
                                "box_position": "GFC"[k % 3], "game_id": game_id,
                                "game_date": date.strftime("%Y-%m-%d"), "season": season,
                                "espn_team_id": str(side), "espn_opponent_id": str(opponent),
                                "is_home": is_home, "starter": k < 5, "minutes": minutes,
                                "points": points, "field_goals_made": fga // 2,
                                "field_goals_attempted": fga, "three_pointers_made": 1,
                                "three_pointers_attempted": 3, "free_throws_made": fta // 2,
                                "free_throws_attempted": fta, "offensive_rebounds": 1,
                                "defensive_rebounds": 3, "rebounds": 4, "assists": 2,
                                "steals": 1, "blocks": 0, "turnovers": int(rng.integers(0, 4)),
                                "personal_fouls": int(rng.integers(0, 5)), "plus_minus": 0,
                                "team_id": TEAMS[side], "team_abbreviation": f"T{side}",
                                "opponent_team_id": TEAMS[opponent],
                                "opponent_abbreviation": f"T{opponent}",
                            }
                        )
                    team_games.append(
                        {
                            "game_id": game_id, "game_date": date.strftime("%Y-%m-%d"),
                            "season": season, "espn_team_id": str(side), "is_home": is_home,
                            "points": team_points, "field_goals_attempted": int(rng.integers(80, 95)),
                            "three_pointers_attempted": int(rng.integers(25, 45)),
                            "free_throws_attempted": int(rng.integers(15, 30)),
                            "offensive_rebounds": int(rng.integers(6, 14)),
                            "turnovers": int(rng.integers(10, 18)), "overtimes": 0,
                            "team_id": TEAMS[side],
                        }
                    )
    players = pd.DataFrame(players)
    team_games = pd.DataFrame(team_games)
    ids = sorted(players["espn_player_id"].unique())
    bios = pd.DataFrame(
        {
            "espn_player_id": ids, "date_of_birth": "1998-01-01T08:00Z",
            "height_in": 78.0, "debut_year": 2020, "bio_position": None,
        }
    )
    id_map = pd.DataFrame({"espn_player_id": ids, "player_id": [int(i) for i in ids]})
    return players, team_games, bios, id_map


def build(tables):
    return ff.build_features(*tables)


# -------------------------------------------------------- brute-force recompute


def recompute(frame, row):
    """Recompute four features for `row` using only rows dated before it."""

    date = row["game_date"]
    own = frame[(frame["player_id"] == row["player_id"]) & (frame["game_date"] < date)]
    own = own.sort_values(["game_date", "game_id"])
    season_rows = own[own["season"] == row["season"]]
    result = {
        "pts_season_avg": season_rows["target_pts"].mean() if len(season_rows) else np.nan,
        "pts_last5_avg": own["target_pts"].tail(5).mean() if len(own) else np.nan,
        "min_ewm": own["target_min"].ewm(span=ff.EWM_SPAN).mean().iloc[-1] if len(own) else np.nan,
    }

    team_season = frame[(frame["team_id"] == row["team_id"]) & (frame["season"] == row["season"])]
    in_game = set(frame.loc[frame["game_id"] == row["game_id"], "player_id"])
    missing, rotation = 0.0, 0
    for player_id in team_season["player_id"].unique():
        history = frame[(frame["player_id"] == player_id) & (frame["game_date"] < date)]
        if history.empty:
            continue
        last = history.sort_values(["game_date", "game_id"]).iloc[-1]
        if last["team_id"] != row["team_id"] or last["season"] != row["season"]:
            continue
        this_season = history[history["season"] == row["season"]]
        if len(this_season) < ff.ROTATION_MIN_GAMES or this_season["target_min"].mean() < ff.ROTATION_MIN_AVG:
            continue
        rotation += 1
        if player_id not in in_game:
            missing += this_season["target_pts"].mean()
    result["missing_ppg"] = missing if rotation else np.nan
    return result


def assert_matches_recomputation(frame, rows, atol=1e-3):
    for _, row in rows.iterrows():
        expected = recompute(frame, row)
        for column, value in expected.items():
            actual = row[column]
            if pd.isna(value):
                assert pd.isna(actual), (column, row["player_id"], row["game_id"], actual)
            else:
                assert actual == pytest.approx(value, abs=atol), (
                    column, row["player_id"], row["game_id"], actual, value,
                )


# ------------------------------------------------------------------------ tests


def test_own_game_stats_do_not_change_own_features():
    tables = make_league()
    base = build(tables)
    target_game = "espn:20240081"

    players, team_games, bios, id_map = (t.copy() for t in tables)
    in_game = players["game_id"] == target_game
    for column in ("points", "minutes", "field_goals_attempted", "free_throws_attempted",
                   "three_pointers_attempted", "turnovers", "personal_fouls"):
        players.loc[in_game, column] = players.loc[in_game, column] + 9
    players.loc[in_game, "starter"] = ~players.loc[in_game, "starter"]
    team_in_game = team_games["game_id"] == target_game
    for column in ("points", "field_goals_attempted", "free_throws_attempted",
                   "turnovers", "offensive_rebounds", "three_pointers_attempted"):
        team_games.loc[team_in_game, column] = team_games.loc[team_in_game, column] + 15
    altered = build((players, team_games, bios, id_map))

    key = ["player_id", "game_id"]
    features = [c for c in base.columns if not c.startswith("target_") and c not in key]
    before = base[base["game_id"] == target_game].set_index(key)[features].sort_index()
    after = altered[altered["game_id"] == target_game].set_index(key)[features].sort_index()
    pd.testing.assert_frame_equal(before, after)

    # The mutation is real: targets and later games do change.
    assert not base["target_pts"].equals(altered["target_pts"])
    later = base["game_date"] > base.loc[base["game_id"] == target_game, "game_date"].iloc[0]
    assert not base.loc[later, "pts_ewm"].equals(altered.loc[later, "pts_ewm"])


def test_features_match_recomputation_from_prior_games():
    frame = build(make_league(skip={("1001", 2024, 9), (STAR, 2024, 10), ("1012", 2023, 7)}))
    rows = frame.sample(150, random_state=0)
    assert_matches_recomputation(frame, rows)


def test_no_same_game_stats_outside_target_columns():
    frame = build(make_league())
    features = ff.feature_columns(frame.columns)
    assert not set(features) & set(ff.TARGETS)
    assert {"target_pts", "target_min"} <= set(frame.columns)
    assert set(frame.columns) == set(ff.FEATURE_DOCS)
    ff.validate(frame, (0, 10**9))


def test_season_average_resets_and_ewm_carries_over():
    frame = build(make_league())
    star = frame[frame["player_id"] == int(STAR)].sort_values("game_date")
    opener = star[star["season"] == 2024].iloc[0]
    last_season = star[star["season"] == 2023]

    assert pd.isna(opener["pts_season_avg"])
    assert opener["games_played_season"] == 0
    assert not pd.isna(opener["pts_ewm"])
    assert opener["prev_season_pts_avg"] == pytest.approx(last_season["target_pts"].mean(), abs=1e-3)
    assert opener["prior_games"] == len(last_season)
    assert pd.isna(star.iloc[0]["pts_ewm"]) and star.iloc[0]["insufficient_history"]


def test_star_absence_counts_as_missing_teammate():
    frame = build(make_league(skip={(STAR, 2024, 8)}))
    star_history = frame[(frame["player_id"] == int(STAR)) & (frame["season"] == 2024)]
    star_history = star_history.sort_values("game_date").head(8)
    missed_game = "espn:20240080"  # team 0 always plays in slot 0

    teammates = frame[frame["game_id"] == missed_game]
    teammates = teammates[teammates["team_id"] == TEAMS[0]]
    assert int(STAR) not in set(teammates["player_id"])
    assert (teammates["missing_ppg"] >= star_history["target_pts"].mean() - 1e-3).all()
    assert (teammates["top3_scorers_out"] >= 1).all()
    assert (teammates["rotation_out"] >= 1).all()

    star_return = frame[(frame["player_id"] == int(STAR)) & (frame["game_id"] == "espn:20240090")]
    assert star_return["games_missed_last14"].iloc[0] == 1
    assert star_return["days_since_last_game"].iloc[0] > 1


def test_parse_summary_fixture_skips_dnp_and_reads_overtime():
    summary = json.loads((FIXTURES / "espn_summary.json").read_text())
    # The fixture predates team box scores; add the minimal block parse_summary reads.
    team_stats = [
        {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "40-88"},
        {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "12-35"},
        {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "20-25"},
        {"name": "offensiveRebounds", "displayValue": "10"},
        {"name": "totalTurnovers", "displayValue": "13"},
    ]
    summary["boxscore"].setdefault(
        "teams", [{"team": {"id": team_id}, "statistics": team_stats} for team_id in ("9", "12")]
    )
    teams = {
        "9": {"id": 1610612744, "abbreviation": "GSW"},
        "12": {"id": 1610612746, "abbreviation": "LAC"},
    }
    players, team_rows = build_dataset.parse_summary(summary, teams, "2025-26")
    assert players and len(team_rows) == 2
    assert {row["season"] for row in players} == {2025}
    assert all(row["game_id"] == f"espn:{summary['header']['id']}" for row in players)
    assert {row["overtimes"] for row in team_rows} == {1}
    dnp = [
        entry["athlete"]["id"]
        for block in summary["boxscore"]["players"]
        for group in block["statistics"]
        for entry in group["athletes"]
        if entry.get("didNotPlay")
    ]
    assert not {str(a) for a in dnp} & {row["espn_player_id"] for row in players}


def test_overtime_periods():
    assert build_dataset.overtime_periods({"type": {"detail": "Final"}}) == 0
    assert build_dataset.overtime_periods({"type": {"detail": "Final/OT"}}) == 1
    assert build_dataset.overtime_periods({"type": {"detail": "Final/3OT"}}) == 3


@pytest.mark.skipif(not REAL_CSV.exists(), reason="data/NBA_player_stats.csv not built")
def test_real_dataset_integrity_and_recomputation():
    frame = pd.read_csv(REAL_CSV, dtype={"game_id": str, "espn_player_id": str})
    assert not frame.duplicated(["player_id", "game_id"]).any()
    assert set(frame["split"]) == {"train", "val", "test"}
    assert not set(ff.feature_columns(frame.columns)) & set(ff.TARGETS)
    rows = frame.sample(200, random_state=491)
    assert_matches_recomputation(frame, rows)
