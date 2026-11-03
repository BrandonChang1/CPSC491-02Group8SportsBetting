"""Read-only readiness checks for the points over/under prediction dataset.

Run from the repository root: python -m data.processing.prediction_readiness
Prints a JSON report and exits 1 if any completeness or validity check fails.
See docs/prop_prediction_dataset_readiness.md for what each check means.
"""
import json
import sys

import pandas as pd
import psycopg

from data.ingestion.database_ingestion import get_database_url
from data.processing.modeling_dataset import MODELING_COLUMNS
from data.processing.points_features import add_points_features
from ml.predict_player import EXPECTED_FEATURE_SCHEMA

# The modeling columns plus the game's teams, needed to validate opponent/home-away.
READINESS_QUERY = """
    SELECT
        pgs.player_id,
        pgs.game_id,
        g.game_date,
        pgs.minutes,
        pgs.points,
        pgs.rebounds,
        pgs.assists,
        pgs.plus_minus,
        pgs.opponent_team_id,
        pgs.is_home,
        pgs.recent_minutes_avg,
        g.home_team_id,
        g.away_team_id
    FROM player_game_stats pgs
    JOIN games g
        ON pgs.game_id = g.id
    ORDER BY
        pgs.player_id,
        g.game_date,
        pgs.game_id
"""

MAX_MINUTES = 70  # Longest NBA games (4+ overtimes) stay under this.
MAX_POINTS = 100
RECENT_MINUTES_TOLERANCE = 0.01


def load_readiness_data() -> pd.DataFrame:
    with psycopg.connect(get_database_url()) as connection:
        cursor = connection.execute(READINESS_QUERY)
        rows = cursor.fetchall()
        columns = [description.name for description in cursor.description]
    data = pd.DataFrame(rows, columns=columns)
    data["game_date"] = pd.to_datetime(data["game_date"])
    return data


def expected_recent_minutes(data: pd.DataFrame) -> pd.Series:
    """Average of the player's previous 5 stored games' minutes, as ingestion's SQL window computes it."""
    minutes = pd.to_numeric(data["minutes"], errors="coerce")
    return minutes.groupby(data["player_id"]).transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )


def readiness_checks(data: pd.DataFrame) -> list[dict]:
    """Return one result per check: the rows that fail it out of the rows it applies to.

    data must be sorted by player_id, game_date, game_id (READINESS_QUERY's order).
    """
    points = pd.to_numeric(data["points"], errors="coerce")
    minutes = pd.to_numeric(data["minutes"], errors="coerce")
    is_home = data["is_home"]
    first_game = ~data["player_id"].duplicated()
    expected_minutes = expected_recent_minutes(data)
    has_teams = data["opponent_team_id"].notna() & is_home.notna()
    expected_opponent = data["away_team_id"].where(is_home.astype("boolean").fillna(False), data["home_team_id"])

    def check(name, field, kind, failing, applies=None):
        applies = pd.Series(True, index=data.index) if applies is None else applies
        return {
            "check": name,
            "field": field,
            "type": kind,
            "rows_checked": int(applies.sum()),
            "failing_rows": int((failing & applies).sum()),
        }

    return [
        check("points present", "points", "completeness", points.isna()),
        check("points is a whole number 0-100", "points", "validity",
              ~points.between(0, MAX_POINTS) | (points % 1 != 0), points.notna()),
        check("minutes present", "minutes", "completeness", minutes.isna()),
        check(f"minutes within 0-{MAX_MINUTES}", "minutes", "validity",
              ~minutes.between(0, MAX_MINUTES), minutes.notna()),
        check("is_home present", "is_home", "completeness", is_home.isna()),
        check("opponent_team_id present", "opponent_team_id", "completeness",
              data["opponent_team_id"].isna()),
        check("opponent/home-away agree with the game's teams", "opponent_team_id, is_home", "validity",
              data["opponent_team_id"] != expected_opponent, has_teams),
        check("recent_minutes_avg present after a player's first game", "recent_minutes_avg", "completeness",
              data["recent_minutes_avg"].isna() & expected_minutes.notna(), ~first_game),
        check("recent_minutes_avg equals the prior-5-game minutes average", "recent_minutes_avg", "validity",
              (data["recent_minutes_avg"].astype(float) - expected_minutes).abs() > RECENT_MINUTES_TOLERANCE,
              data["recent_minutes_avg"].notna() & expected_minutes.notna()),
        check("recent_minutes_avg empty on a player's first game", "recent_minutes_avg", "validity",
              data["recent_minutes_avg"].notna(), first_game),
        check("one row per player per game date", "player_id, game_date", "validity",
              data.duplicated(["player_id", "game_date"], keep=False)),
    ]


def build_prediction_features(data: pd.DataFrame) -> pd.DataFrame:
    """Build the model's feature table from stored rows, in the dtypes the served model expects."""
    games = data[MODELING_COLUMNS].copy()
    games["points"] = pd.to_numeric(games["points"], errors="coerce")
    games["recent_minutes_avg"] = pd.to_numeric(games["recent_minutes_avg"], errors="coerce")
    games = add_points_features(games.dropna(subset=["points"]))
    games["is_home"] = games["is_home"].astype(bool)
    return games


def feature_schema_mismatches(features: pd.DataFrame) -> list[str]:
    return [
        f"{name}: expected {dtype}, got {features[name].dtype if name in features else 'missing'}"
        for name, dtype in EXPECTED_FEATURE_SCHEMA
        if name not in features or str(features[name].dtype) != dtype
    ]


def history_coverage(features: pd.DataFrame) -> dict:
    games_per_player = features.groupby("player_id").size()
    feature_names = [name for name, _ in EXPECTED_FEATURE_SCHEMA]
    return {
        "rows": len(features),
        "players": int(features["player_id"].nunique()),
        "first_game": features["game_date"].min().strftime("%Y-%m-%d"),
        "last_game": features["game_date"].max().strftime("%Y-%m-%d"),
        "rows_by_season": {
            f"{season}-{str(season + 1)[-2:]}": int(count)
            for season, count in features.groupby("season").size().items()
        },
        "players_with_at_least_10_games": int((games_per_player >= 10).sum()),
        "feature_null_rows": {name: int(features[name].isna().sum()) for name in feature_names},
        "rows_with_all_features": int(features[feature_names].notna().all(axis=1).sum()),
    }


def readiness_report(data: pd.DataFrame) -> dict:
    checks = readiness_checks(data)
    features = build_prediction_features(data)
    schema_problems = feature_schema_mismatches(features)
    return {
        "ready": not schema_problems and all(result["failing_rows"] == 0 for result in checks),
        "checks": checks,
        "feature_schema_problems": schema_problems,
        "coverage": history_coverage(features),
    }


def main():
    report = readiness_report(load_readiness_data())
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
