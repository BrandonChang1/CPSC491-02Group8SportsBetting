"""Fetch player game logs from ESPN for the prediction route.

Usage: python ml/fetch_nba_history.py PLAYER_ID
Prints one JSON result to stdout; diagnostics go to stderr.
"""
import json
import math
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.collection.espn import game_date, player_events


def seasons_to_try(now=None):
    now = now or datetime.now(timezone.utc)
    start_year = now.year if now.month >= 10 else now.year - 1
    return [f"{year}-{str(year + 1)[-2:]}" for year in (start_year, start_year - 1)]


def fetch_games(player_id):
    games = {}
    errors = []
    for season in seasons_to_try():
        try:
            for event_id, event in player_events(player_id, season).items():
                try:
                    date = game_date(event["gameDate"])
                    value = float(event["stats"]["points"])
                    if not math.isfinite(value) or value < 0:
                        continue
                    games[(date, event_id)] = {"game_date": date, "points": value}
                except (ValueError, TypeError):
                    continue
        except Exception as exc:  # noqa: BLE001 External API errors vary by version
            errors.append(f"{season}: {exc}")
    ordered = sorted(games.values(), key=lambda game: game["game_date"])
    return {
        "success": bool(ordered),
        "games": ordered,
        "message": "No NBA game history available from ESPN." if not ordered else "",
        "errors": errors,
    }


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print(json.dumps({"success": False, "games": [], "message": "Valid player ID required."}))
        return
    print(json.dumps(fetch_games(int(sys.argv[1]))))


if __name__ == "__main__":
    main()
