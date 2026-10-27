"""Batch Random Forest projections for experimental team matchup estimates."""
import json
import math
import sys

from predict_player import predict


def estimate(team_players):
    projections = []
    latest_game = None
    historical_roster_players = 0
    for player in team_players[:15]:
        result = predict(player.get("games", []))
        points = result.get("predictedPoints")
        if not result.get("success") or result.get("gamesAvailable", 0) < 3:
            continue
        if not isinstance(points, (float, int)) or not math.isfinite(points):
            continue
        projections.append(float(points))
        if player.get("rosterSource") == "latest_historical_game":
            historical_roster_players += 1
        date = player.get("lastGameDate") or result.get("lastGameDate")
        if date and (latest_game is None or date > latest_game):
            latest_game = date
    if not projections:
        return None
    # A comparable eight-player scoring index, not a team's actual score.
    return {
        "projectedPoints": round(sum(projections) / len(projections) * 8, 2),
        "playersUsed": len(projections),
        "coverage": "limited" if len(projections) < 5 else "normal",
        "latestGameDate": latest_game,
        "historicalRosterPlayers": historical_roster_players,
    }


def main():
    payload = json.load(sys.stdin)
    teams = {}
    for tricode, players in payload.get("teams", {}).items():
        teams[tricode] = estimate(players)
    print(json.dumps({"success": True, "teams": teams}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        sys.exit(1)
