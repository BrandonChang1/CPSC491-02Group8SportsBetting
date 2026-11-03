"""Shared evaluation contract for next-game points models (SEC-05, SCRUM-112).

Every candidate model and every baseline is scored here, on one held-out
period, so model updates are compared consistently before approval:

- load_dataset() ignores the CSV's precomputed `split` column. That column
  put a single player's season in test (the one-player holdout issue).
- holdout_split() applies one eligibility rule to all rows, then a
  chronological split weighted by rows, and refuses a holdout that covers
  too few players or overlaps train in time.
- score_holdout() scores every prediction set against the same test rows
  and raises if any set was produced for different rows.

The baseline comparison (best_baseline, beats_best_baseline) is recorded for
reviewers only. Approval does not depend on beating a baseline or on any
score; it only requires that the approved artifact is the one evaluated.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from data.processing.points_features import time_split

TARGET = "points"
FEATURES = ["pts_season_avg", "pts_last5_avg", "pts_last10_avg", "is_home", "recent_minutes_avg"]
# Baseline name -> the feature column it predicts with.
BASELINES = {
    "Season avg": "pts_season_avg",
    "Last 5 avg": "pts_last5_avg",
    "Last 10 avg": "pts_last10_avg",
}
TRAIN_FRACTION = 0.8
MIN_TEST_PLAYERS = 10


class HoldoutError(ValueError):
    """The held-out period cannot give a fair, leakage-free evaluation."""


@dataclass(frozen=True)
class Holdout:
    train: pd.DataFrame
    test: pd.DataFrame

    def summary(self):
        def period(frame):
            return {
                "rows": len(frame),
                "players": int(frame["player_id"].nunique()),
                "first_game": frame["game_date"].min().strftime("%Y-%m-%d"),
                "last_game": frame["game_date"].max().strftime("%Y-%m-%d"),
            }

        test_by_season = self.test.groupby("season").agg(rows=(TARGET, "size"), players=("player_id", "nunique"))
        return {
            "method": f"chronological, first {TRAIN_FRACTION:.0%} of eligible rows by game date (time_split by='rows')",
            "eligibility": f"rows with {TARGET} and every baseline feature present: {list(BASELINES.values())}",
            "train": period(self.train),
            "test": period(self.test),
            "test_rows_by_season": {
                f"{season}-{str(season + 1)[-2:]}": {"rows": int(row.rows), "players": int(row.players)}
                for season, row in test_by_season.iterrows()
            },
        }


def load_dataset(path):
    data = pd.read_csv(path, dtype={"game_id": str})
    data["game_date"] = pd.to_datetime(data["game_date"], format="%Y-%m-%d")
    for column in [*FEATURES, TARGET]:
        if column != "is_home":
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data["is_home"] = data["is_home"].astype(bool)
    return data.drop(columns="split", errors="ignore")


def holdout_split(data, train_fraction=TRAIN_FRACTION, min_test_players=MIN_TEST_PLAYERS):
    """Split eligible rows by date; train and test share no date and test covers many players."""
    eligible = data.dropna(subset=[TARGET, *BASELINES.values()])
    labelled = time_split(eligible, train_fraction=train_fraction, by="rows")
    train = labelled[labelled["split"] == "train"]
    test = labelled[labelled["split"] == "test"]

    if train.empty or test.empty or train["game_date"].max() >= test["game_date"].min():
        raise HoldoutError("Train must end before the held-out period starts")
    if test["player_id"].nunique() < min_test_players:
        raise HoldoutError(
            f"Held-out period covers {test['player_id'].nunique()} player(s); need at least {min_test_players}"
        )
    return Holdout(train=train, test=test)


def regression_metrics(actual, predicted):
    return {
        "n": len(actual),
        "MAE": round(float(mean_absolute_error(actual, predicted)), 3),
        "RMSE": round(float(np.sqrt(mean_squared_error(actual, predicted))), 3),
        "R2": round(float(r2_score(actual, predicted)), 3),
    }


def score_holdout(test, predictions):
    """Score each named prediction set on exactly the rows of `test`.

    Baseline predictions are added here from `test` itself, so models and
    baselines cannot be scored on different rows or periods.
    """
    scored = {name: test[column] for name, column in BASELINES.items()}
    for name, values in predictions.items():
        if isinstance(values, pd.Series):
            if not values.index.equals(test.index):
                raise HoldoutError(f"Predictions for {name!r} are not for the held-out rows")
        elif len(values) != len(test):
            raise HoldoutError(f"Predictions for {name!r} have {len(values)} rows; holdout has {len(test)}")
        scored[name] = values
    return {name: regression_metrics(test[TARGET], values) for name, values in scored.items()}


def evaluate_model(model, holdout, name):
    """Score a trained model and every baseline on the holdout, overall and per season."""
    test_scores = score_holdout(holdout.test, {name: model.predict(holdout.test[FEATURES])})
    baseline_names = list(BASELINES)
    best_baseline = min(baseline_names, key=lambda key: test_scores[key]["MAE"])
    by_season = {}
    for season, rows in holdout.test.groupby("season"):
        label = f"{season}-{str(season + 1)[-2:]}"
        by_season[label] = score_holdout(rows, {name: model.predict(rows[FEATURES])})
    return {
        "model": name,
        "train": regression_metrics(holdout.train[TARGET], model.predict(holdout.train[FEATURES])),
        "test": test_scores[name],
        "baselines_test": {key: test_scores[key] for key in baseline_names},
        "best_baseline": best_baseline,
        "beats_best_baseline": test_scores[name]["MAE"] < test_scores[best_baseline]["MAE"],
        "test_by_season": by_season,
    }
