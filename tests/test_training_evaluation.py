"""SEC-05 tests (SCRUM-112): chronological holdout, shared baseline/model evaluation, leakage.

Complements tests/test_time_split.py and tests/test_points_features.py, which
cover the feature and split primitives on synthetic data.
"""
from pathlib import Path

import pandas as pd
import pytest

from data.processing.modeling_features import add_modeling_context
from data.processing.points_features import (
    FEATURE_COLS,
    add_points_features,
    time_split,
)
from ml.training import evaluation
from ml.training.evaluation import (
    BASELINES,
    MIN_TEST_PLAYERS,
    HoldoutError,
    holdout_split,
    load_dataset,
    score_holdout,
)

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
TRAINING_DATA = SAMPLE / "player_game_stats_sample_features.csv"
RAW_DATA = SAMPLE / "player_game_stats_sample.csv"


def games_with_sparse_tail(players=20, dense_days=50, tail_days=30):
    """Many players for dense_days, then one player alone for tail_days (the shape of the sample data)."""
    dense = pd.date_range("2025-01-01", periods=dense_days, freq="D")
    tail = pd.date_range(dense[-1] + pd.Timedelta(days=1), periods=tail_days, freq="D")
    rows = [{"player_id": p, "game_date": d} for p in range(players) for d in dense]
    rows += [{"player_id": 0, "game_date": d} for d in tail]
    games = pd.DataFrame(rows)
    games["points"] = 10.0
    games["season"] = 2024
    for column in BASELINES.values():
        games[column] = 10.0
    return games


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(TRAINING_DATA)


# --- time_split(by="rows") -----------------------------------------------


def test_row_split_never_splits_a_date_and_keeps_train_before_test():
    split = time_split(games_with_sparse_tail(), by="rows")

    assert split.groupby("game_date")["split"].nunique().eq(1).all()
    assert split.loc[split["split"] == "train", "game_date"].max() < split.loc[split["split"] == "test", "game_date"].min()
    assert len(split[split["split"] == "train"]) / len(split) <= 0.8


def test_date_split_leaves_one_player_where_row_split_does_not():
    games = games_with_sparse_tail()

    by_dates = time_split(games, by="dates")
    by_rows = time_split(games, by="rows")

    assert by_dates.loc[by_dates["split"] == "test", "player_id"].nunique() == 1
    assert by_rows.loc[by_rows["split"] == "test", "player_id"].nunique() == 20


def test_unknown_split_mode_raises():
    with pytest.raises(ValueError):
        time_split(games_with_sparse_tail(), by="players")


# --- The one-player holdout issue on the committed training data ----------


def test_committed_split_column_is_the_one_player_holdout():
    # Documents the original issue: the CSV's precomputed split tests on one player.
    raw = pd.read_csv(TRAINING_DATA)
    assert raw.loc[raw["split"] == "test", "player_id"].nunique() == 1


def test_holdout_ignores_csv_split_and_covers_many_players(dataset):
    assert "split" not in dataset.columns

    holdout = holdout_split(dataset)

    assert holdout.test["player_id"].nunique() >= MIN_TEST_PLAYERS
    assert holdout.train["game_date"].max() < holdout.test["game_date"].min()
    assert not set(holdout.train["game_date"]) & set(holdout.test["game_date"])
    assert len(holdout.train) + len(holdout.test) == len(dataset.dropna(subset=["points", *BASELINES.values()]))


def test_holdout_refuses_too_few_test_players():
    with pytest.raises(HoldoutError, match="player"):
        holdout_split(games_with_sparse_tail(players=3), min_test_players=MIN_TEST_PLAYERS)


# --- Baseline and model scored on the same rows ---------------------------


def test_model_and_baselines_are_scored_on_identical_rows(dataset):
    holdout = holdout_split(dataset)
    seen = []

    class RecordingModel:
        def predict(self, frame):
            seen.append(frame.index)
            return frame["pts_last5_avg"].to_numpy()

    metrics = evaluation.evaluate_model(RecordingModel(), holdout, "candidate")

    assert any(index.equals(holdout.test.index) for index in seen)
    assert any(index.equals(holdout.train.index) for index in seen)
    # Every other call is a per-season slice of the same held-out rows.
    assert all(index.isin(holdout.test.index).all() or index.equals(holdout.train.index) for index in seen)
    assert {m["n"] for m in metrics["baselines_test"].values()} == {metrics["test"]["n"]} == {len(holdout.test)}
    # A model that predicts the last-5 average must score exactly like that baseline.
    assert metrics["test"] == metrics["baselines_test"]["Last 5 avg"]


def test_predictions_for_other_rows_are_rejected(dataset):
    test = holdout_split(dataset).test

    with pytest.raises(HoldoutError):
        score_holdout(test, {"model": test["points"].iloc[1:]})
    with pytest.raises(HoldoutError):
        score_holdout(test, {"model": test["points"].reset_index(drop=True)})
    with pytest.raises(HoldoutError):
        score_holdout(test, {"model": [1.0, 2.0]})


# --- Leakage in the committed training data -------------------------------


def test_committed_training_features_use_only_prior_games():
    """Recompute every model feature from the raw logs with the prior-games-only code."""
    raw = pd.read_csv(RAW_DATA, dtype={"game_id": str}, parse_dates=["game_date"])
    recomputed = add_modeling_context(add_points_features(raw.drop(columns=["recent_minutes_avg"])))
    committed = pd.read_csv(TRAINING_DATA, dtype={"game_id": str}, parse_dates=["game_date"])

    merged = committed.merge(recomputed, on=["player_id", "game_id"], suffixes=("", "_recomputed"), validate="1:1")
    assert len(merged) == len(committed)
    for column in [*FEATURE_COLS, "recent_minutes_avg"]:
        pd.testing.assert_series_equal(merged[column], merged[f"{column}_recomputed"], check_names=False, atol=1e-9)
