"""Offline checks for the research handoff's source filtering and feature timing."""

import copy
import io
import json

import pandas as pd
import pytest

from scripts.build_espn_feature_sample import (
    DIRECTORY,
    FEATURES,
    build_features,
    load_source,
)


@pytest.fixture
def snapshot():
    return json.loads((DIRECTORY / "source_game_logs.json").read_text())


def test_export_matches_snapshot_and_has_chronological_holdout(snapshot):
    features = build_features(load_source(snapshot))
    rebuilt = pd.read_csv(io.StringIO(features.to_csv(
        index=False, date_format="%Y-%m-%d", float_format="%.4f",
    )))
    stored = pd.read_csv(DIRECTORY / "points_training.csv")
    pd.testing.assert_frame_equal(rebuilt, stored)
    assert len(stored) == 575
    assert not stored.duplicated(["player_id", "game_id"]).any()
    assert stored.loc[stored["split"] == "train", "game_date"].max() < stored.loc[
        stored["split"] == "test", "game_date"
    ].min()


def test_current_outcomes_do_not_change_own_features(snapshot):
    games = load_source(snapshot)
    original = build_features(games)
    row = original[original["prior_games_count"] >= 10].iloc[0]
    key = (games["player_id"] == row["player_id"]) & (games["game_id"] == row["game_id"])
    for column in ["points", "minutes", "field_goals_attempted", "field_goal_pct",
                   "free_throws_attempted", "three_pointers_attempted"]:
        games.loc[key, column] = 0
    changed = build_features(games)
    pd.testing.assert_series_equal(original.loc[row.name, FEATURES], changed.loc[row.name, FEATURES])


def test_rolling_windows_player_isolation_and_season_transition(snapshot):
    features = build_features(load_source(snapshot))
    for _, player in features.groupby("player_id"):
        player = player.sort_values("game_date").reset_index(drop=True)
        assert player.loc[0, [f for f in FEATURES if f != "is_home"]].isna().all()
        for index in [1, 10, len(player) - 1]:
            previous = player.iloc[max(0, index - 5):index]
            assert player.loc[index, "fga_last5_avg"] == pytest.approx(previous["actual_field_goals_attempted"].mean(), abs=0.0001)
            assert player.loc[index, "fg_pct_last5_avg"] == pytest.approx(previous["actual_field_goal_pct"].mean(), abs=0.0001)
            assert player.loc[index, "days_since_last_game"] == (player.loc[index, "game_date"] - player.loc[index - 1, "game_date"]).days
        first_new_season = player[player["season_end_year"] == 2026].iloc[0]
        assert pd.isna(first_new_season["pts_season_avg"])
        assert first_new_season["prior_games_count"] > 10
        assert pd.notna(first_new_season["pts_last10_avg"])


def test_exhibition_teams_are_excluded_and_bad_stats_fail(snapshot):
    sample = copy.deepcopy(snapshot)
    sample["sources"] = sample["sources"][:1]
    source = sample["sources"][0]
    valid = next(e for e in source["events"] if e["metadata"]["homeTeamId"] == "9")
    source["events"] = [copy.deepcopy(valid)]
    exhibition = copy.deepcopy(valid)
    exhibition["eventId"] = "all-star"
    exhibition["metadata"]["homeTeamId"] = "130580"
    source["events"].append(exhibition)
    assert len(load_source(sample)) == 1
    source["events"][0]["stats"][source["names"].index("fieldGoalsMade-fieldGoalsAttempted")] = "9-2"
    with pytest.raises(ValueError, match="Invalid shooting stats"):
        load_source(sample)
