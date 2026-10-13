"""Fetch player game logs from nba_api for the prediction route.

Usage: python ml/fetch_nba_history.py PLAYER_ID
Prints one JSON result to stdout; diagnostics go to stderr.
"""
import json
import sys
from datetime import datetime, timezone

from nba_api.stats.endpoints import playergamelog


def seasons_to_try(now=None):
    now = now or datetime.now(timezone.utc)
    start_year = now.year if now.month >= 10 else now.year - 1
    return [f"{year}-{str(year + 1)[-2:]}" for year in (start_year, start_year - 1)]


def fetch_games(player_id):
    games = {}
    errors = []
    for season in seasons_to_try():
        try:
            response = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season,
                season_type_all_star="Regular Season",
                timeout=15,
            )
            frame = response.get_data_frames()[0]
            for _, row in frame.iterrows():
                date = str(row.get("GAME_DATE", "")).strip()
                points = row.get("PTS")
                if date and points is not None:
                    try:
                        value = float(points)
                        if value != value:  # NaN
                            continue
                        games[(date, str(row.get("Game_ID", "")))] = {
                            "game_date": date, "points": value,
                        }
                    except (ValueError, TypeError):
                        continue
        except Exception as exc:  # noqa: BLE001 External API errors vary by version
            errors.append(f"{season}: {exc}")
    ordered = sorted(games.values(), key=lambda game: game["game_date"])
    return {
        "success": bool(ordered),
        "games": ordered,
        "message": "No NBA game history available from nba_api." if not ordered else "",
        "errors": errors,
    }


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print(json.dumps({"success": False, "games": [], "message": "Valid player ID required."}))
        return
    print(json.dumps(fetch_games(int(sys.argv[1]))))


if __name__ == "__main__":
    main()
