"""ML-TEST-02: time-split and leakage tests."""

from pathlib import Path

import pandas as pd
import pytest

from data.processing.points_features import (
    FEATURE_COLS,
    add_points_features,
    time_split,
)

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "sample"
    / "sample_player_game_logs.csv"
)


def make_games(dates_count=10, player_ids=(1,)):
    dates = pd.date_range("2025-11-01", periods=dates_count, freq="D")

    return pd.DataFrame(
        [
            {"player_id": player_id, "game_date": date, "points": 10 + i}
            for player_id in player_ids
            for i, date in enumerate(dates)
        ]
    )


def test_split_is_80_20_by_date():
    split = time_split(make_games(10))

    assert split.loc[split["split"] == "train", "game_date"].nunique() == 8
    assert split.loc[split["split"] == "test", "game_date"].nunique() == 2


def test_train_dates_all_before_test_dates():
    split = time_split(make_games(10))

    train = split[split["split"] == "train"]
    test = split[split["split"] == "test"]

    assert train["game_date"].max() < test["game_date"].min()


def test_same_date_never_in_both_splits():
    split = time_split(make_games(10, player_ids=(1, 2, 3)))

    splits_per_date = split.groupby("game_date")["split"].nunique()

    assert splits_per_date.eq(1).all()


def test_split_keeps_every_row():
    games = make_games(10, player_ids=(1, 2))

    split = time_split(games)

    assert len(split) == len(games)
    assert set(split["split"]) == {"train", "test"}


@pytest.mark.parametrize("fraction", [0, 1, -0.2, 1.5])
def test_invalid_fraction_raises(fraction):
    with pytest.raises(ValueError):
        time_split(make_games(10), train_fraction=fraction)


def test_single_date_raises():
    with pytest.raises(ValueError):
        time_split(make_games(1, player_ids=(1, 2)))


def test_changing_future_game_does_not_change_past_features():
    games = make_games(10, player_ids=(1, 2))
    last_date = games["game_date"].max()

    changed = games.copy()
    changed.loc[changed["game_date"] == last_date, "points"] = 99

    original_features = add_points_features(games)
    changed_features = add_points_features(changed)

    is_past = original_features["game_date"] < last_date

    pd.testing.assert_frame_equal(
        original_features.loc[is_past, FEATURE_COLS],
        changed_features.loc[is_past, FEATURE_COLS],
    )


def test_train_features_independent_of_test_rows():
    games = time_split(make_games(10, player_ids=(1, 2)))
    train_games = games[games["split"] == "train"]

    full_features = add_points_features(games)
    train_only_features = add_points_features(train_games)

    pd.testing.assert_frame_equal(
        full_features[full_features["split"] == "train"].reset_index(drop=True),
        train_only_features,
    )


def test_sample_data_features_use_only_prior_games():
    games = pd.read_csv(
        SAMPLE_PATH,
        dtype={"game_id": str},
        parse_dates=["game_date"],
    )

    features = time_split(add_points_features(games))

    for _, player_games in features.groupby("player_id"):
        rows = player_games.reset_index(drop=True)
        points = rows["points"].tolist()

        assert rows.loc[0, FEATURE_COLS].isna().all()

        for i in range(1, len(rows)):
            prev = points[:i]
            # The sample covers a single season, so the season average
            # uses every earlier game.
            assert rows.loc[i, "pts_season_avg"] == round(sum(prev) / len(prev), 2)
            assert rows.loc[i, "pts_last5_avg"] == round(sum(prev[-5:]) / len(prev[-5:]), 2)
            assert rows.loc[i, "pts_last10_avg"] == round(sum(prev[-10:]) / len(prev[-10:]), 2)

    train = features[features["split"] == "train"]
    test = features[features["split"] == "test"]

    assert len(test) > 0
    assert train["game_date"].max() < test["game_date"].min()
