"""Next-game points baseline predictions from database game history passed as JSON.

Reads {'games': [{'game_date': 'YYYY-MM-DD', 'points': 12}, ...]} on stdin.
Outputs one JSON result on stdout, suitable for the Express route.
"""
import json
import sys
from pathlib import Path

import pandas as pd

# Import the project's existing season calculation rather than duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.processing.points_features import assign_season  # noqa: E402


def predict(games):
    df = pd.DataFrame(games)
    if df.empty or not {"game_date", "points"}.issubset(df.columns):
        return {"success": False, "message": "No historical games available for predictions."}
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df["points"] = pd.to_numeric(df["points"], errors="coerce")
    df = df.dropna(subset=["game_date", "points"]).sort_values("game_date")
    if df.empty:
        return {"success": False, "message": "No valid game history available."}
    df["season"] = assign_season(df["game_date"])
    latest_season = int(df.iloc[-1]["season"])
    season_games = df[df["season"] == latest_season]
    return {
        "success": True,
        "model": "Historical points-average baselines (not a trained ML model)",
        "season": f"{latest_season}-{str(latest_season + 1)[-2:]}",
        "lastGameDate": df.iloc[-1]["game_date"].strftime("%Y-%m-%d"),
        "gamesAvailable": len(df),
        "predictions": {
            "season": round(float(season_games["points"].mean()), 2),
            "last5": round(float(df["points"].tail(5).mean()), 2),
            "last10": round(float(df["points"].tail(10).mean()), 2),
        },
        "note": "These are next-game points baselines, not guaranteed outcomes or forecasts for specific matchups.",
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
