"""Next-game random-forest points predictions from game history passed as JSON.

Reads {'games': [{'game_date': 'YYYY-MM-DD', 'points': 12}, ...]} on stdin.
Outputs one JSON result on stdout, suitable for the Express route.
"""
import json
from functools import lru_cache
import math
import sys
from pathlib import Path

import joblib
import pandas as pd

# Import the project's existing season calculation rather than duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.processing.points_features import assign_season  # noqa: E402

MODEL_PATH = Path(__file__).resolve().parent / "models" / "artifacts" / "random_forest_points.joblib"
<<<<<<< Updated upstream
=======


@lru_cache(maxsize=1)
def load_model():
    return joblib.load(MODEL_PATH)
>>>>>>> Stashed changes


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
        # Only load the model artifact committed by the project team;
        # joblib files should never be accepted from user uploads.
        artifact = load_model()
        feature_names = artifact["features"]
        if set(feature_names) != set(features):
            raise ValueError("Saved model features do not match prediction inputs")
        estimate = float(artifact["pipeline"].predict(pd.DataFrame([features])[feature_names])[0])
        if not math.isfinite(estimate):
            raise ValueError("Saved model returned an invalid estimate")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"success": False, "message": f"Trained points model unavailable: {exc}"}

    return {
        "success": True,
        "predictedPoints": round(max(0.0, estimate), 2),
        "modelVersion": "random-forest-points-v1",
        "missingContext": [key for key in ("is_home", "recent_minutes_avg") if math.isnan(features[key])],
<<<<<<< Updated upstream
        "model": "Trained random forest (tree-based points regression)",
=======
        "model": "Random forest (tree-based ML points)",
>>>>>>> Stashed changes
        "season": f"{latest_season}-{str(latest_season + 1)[-2:]}",
        "lastGameDate": df.iloc[-1]["game_date"].strftime("%Y-%m-%d"),
        "gamesAvailable": len(df),
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
