"""ML-TEST-01: feature-engineering unit tests."""

import pandas as pd

from data.processing.points_features import (
    FEATURE_COLS,
    add_points_features,
)


def make_games(points, player_id=1, start="2025-11-01"):
    return pd.DataFrame(
        {
            "player_id": player_id,
            "game_date": pd.date_range(start, periods=len(points), freq="2D"),
            "points": points,
        }
    )


def test_last5_and_last10_use_previous_games():
    points = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]

    features = add_points_features(make_games(points))

    # Game 7 (index 6): previous 6 games are 10..60.
    assert features.loc[6, "pts_last5_avg"] == 40.0  # mean(20..60)
    assert features.loc[6, "pts_last10_avg"] == 35.0  # mean(10..60)

    # Game 12 (index 11): previous 11 games are 10..110.
    assert features.loc[11, "pts_last5_avg"] == 90.0  # mean(70..110)
    assert features.loc[11, "pts_last10_avg"] == 65.0  # mean(20..110)
    assert features.loc[11, "pts_season_avg"] == 60.0  # mean(10..110)


def test_first_game_has_no_features():
    features = add_points_features(make_games([25, 30, 35]))

    assert features.loc[0, FEATURE_COLS].isna().all()


def test_short_history_averages_available_games():
    features = add_points_features(make_games([12, 18, 24, 30]))

    assert features.loc[1, FEATURE_COLS].tolist() == [12.0, 12.0, 12.0]
    assert features.loc[3, FEATURE_COLS].tolist() == [18.0, 18.0, 18.0]


def test_current_game_points_not_in_own_features():
    features = add_points_features(make_games([20, 20, 20, 20, 60]))

    assert features.loc[4, FEATURE_COLS].tolist() == [20.0, 20.0, 20.0]


def test_players_are_kept_separate():
    games = pd.concat(
        [
            make_games([10, 10, 10], player_id=1, start="2025-11-01"),
            make_games([40, 40, 40], player_id=2, start="2025-11-02"),
        ]
    )

    features = add_points_features(games)

    player_1 = features[features["player_id"] == 1]
    player_2 = features[features["player_id"] == 2]

    assert player_1["pts_last5_avg"].dropna().eq(10.0).all()
    assert player_2["pts_last5_avg"].dropna().eq(40.0).all()
    assert player_2["pts_last5_avg"].isna().sum() == 1


def test_season_average_resets_at_new_season():
    games = pd.DataFrame(
        {
            "player_id": 1,
            "game_date": pd.to_datetime(
                ["2025-03-30", "2025-04-10", "2025-10-22", "2025-10-24"]
            ),
            "points": [10, 20, 30, 40],
        }
    )

    features = add_points_features(games)

    assert features["season"].tolist() == [2024, 2024, 2025, 2025]

    # First game of the new season: no season average yet,
    # but the recent-form averages carry over.
    assert pd.isna(features.loc[2, "pts_season_avg"])
    assert features.loc[2, "pts_last5_avg"] == 15.0
    assert features.loc[3, "pts_season_avg"] == 30.0


def test_unsorted_input_and_no_mutation():
    games = make_games([5, 15, 25, 35, 45, 55])
    shuffled = games.sample(frac=1, random_state=0)
    shuffled_before = shuffled.copy()

    sorted_features = add_points_features(games)
    shuffled_features = add_points_features(shuffled)

    pd.testing.assert_frame_equal(sorted_features, shuffled_features)
    pd.testing.assert_frame_equal(shuffled, shuffled_before)


def test_features_rounded_to_two_decimals():
    features = add_points_features(make_games([10, 10, 11, 5]))

    # mean(10, 10, 11) = 10.333...
    assert features.loc[3, "pts_last5_avg"] == 10.33
