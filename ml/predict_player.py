"""Next-game random-forest points predictions from game history passed as JSON.

Reads {'games': [{'game_date': 'YYYY-MM-DD', 'points': 12}, ...]} on stdin.
Outputs one JSON result on stdout, suitable for the Express route.
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

# Import the project's existing season calculation rather than duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.processing.points_features import assign_season  # noqa: E402
from ml.model_integrity import ModelIntegrityError, load_verified_model  # noqa: E402

MODEL_PATH = Path(__file__).resolve().parent / "models" / "artifacts" / "linear_regression_points.joblib"
MODEL_NAME = "linear-regression-points"
SUPPORTED_MAJOR_VERSIONS = {1}
# Ordered (name, training dtype) pairs this code builds; the model's manifest must match exactly.
EXPECTED_FEATURE_SCHEMA = [
    ("pts_season_avg", "float64"),
    ("pts_last5_avg", "float64"),
    ("pts_last10_avg", "float64"),
    ("is_home", "int64"),
    ("recent_minutes_avg", "float64"),
]


def load_model():
    """Load the points model only after it passes manifest verification."""
    return load_verified_model(
        MODEL_PATH,
        model_name=MODEL_NAME,
        supported_major_versions=SUPPORTED_MAJOR_VERSIONS,
        expected_feature_schema=EXPECTED_FEATURE_SCHEMA,
    )
from data.processing.points_features import assign_season

MODEL_PATH = Path(__file__).resolve().parent / "models" / "artifacts" / "random_forest_points.joblib"

def load_model():
    return joblib.load(MODEL_PATH)


def predict(games):
    df = pd.DataFrame(games)
    if df.empty or not {"game_date", "points"}.issubset(df.columns):
        return {"success": False, "message": "No historical games available for predictions."}
    df["game_date"] = pd.to_datetime(df["game_date"], format="%Y-%m-%d", errors="coerce")
    df["points"] = pd.to_numeric(df["points"], errors="coerce")
    if "minutes" in df:
        df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce")
    df = df.dropna(subset=["game_date", "points"]).sort_values("game_date")
    if df.empty:
        return {"success": False, "message": "No valid game history available."}
    df["season"] = assign_season(df["game_date"])
    latest_season = int(df.iloc[-1]["season"])
    season_games = df[df["season"] == latest_season]
    # These are the same feature definitions used when training the saved pipeline.
    # Since the future opponent/venue is unknown, do not infer home/away from
    # the last played game. The trained imputer fills the missing context.
    features = {
        "pts_season_avg": float(season_games["points"].mean()),
        "pts_last5_avg": float(df["points"].tail(5).mean()),
        "pts_last10_avg": float(df["points"].tail(10).mean()),
        "is_home": float("nan"),
        "recent_minutes_avg": (
            float(df["minutes"].dropna().tail(5).mean())
            if "minutes" in df and df["minutes"].notna().any()
            else float("nan")
        ),
    }
    try:
        # Only artifacts whose bytes match a committed manifest are deserialized;
        # joblib files should never be accepted from user uploads.
        model = load_model()
        feature_names = [name for name, _ in EXPECTED_FEATURE_SCHEMA]
        estimate = float(model.artifact["pipeline"].predict(pd.DataFrame([features])[feature_names])[0])
        if not math.isfinite(estimate):
            raise ValueError("Saved model returned an invalid estimate")
    except ModelIntegrityError as exc:
        # Full details (paths, hashes) go to the server log, not the API client.
        print(f"Model integrity verification failed: {exc}", file=sys.stderr)
        return {
            "success": False,
            "errorCode": exc.code,
            "message": "Trained points model unavailable: the model failed integrity verification.",
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"success": False, "message": f"Trained points model unavailable: {exc}"}

    return {
        "success": True,
        "predictedPoints": round(max(0.0, estimate), 2),
        "modelVersion": model.model_version,
        "missingContext": [key for key in ("is_home", "recent_minutes_avg") if math.isnan(features[key])],
        "model": "Trained linear regression (points)",
        "model": "Trained random forest (tree-based points regression)",
        "season": f"{latest_season}-{str(latest_season + 1)[-2:]}",
        "lastGameDate": df.iloc[-1]["game_date"].strftime("%Y-%m-%d"),
        "gamesAvailable": len(df),
        "predictions": {
            "season": round(float(season_games["points"].mean()), 2),
            "last5": round(float(df["points"].tail(5).mean()), 2),
            "last10": round(float(df["points"].tail(10).mean()), 2),
        },
        "note": "Model estimate for a hypothetical next game, not a specific matchup or guaranteed outcome. Unknown inputs are imputed.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(predict(payload.get("games", []))))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
