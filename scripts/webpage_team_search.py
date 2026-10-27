import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.collection import espn as teams


def find_team(team_name):
    nba_teams = teams.get_teams()

    team_name = team_name.lower()

    for team in nba_teams:
        full_name = team["full_name"].lower()
        nickname = team["nickname"].lower()
        city = team["city"].lower()
        abbreviation = team["abbreviation"].lower()

        if (
            team_name == full_name
            or team_name == nickname
            or team_name == city
            or team_name == abbreviation
        ):
            return team

    return None


def main():

    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "message": "No team name was provided.",
            "data": []
        }))
        return

    team_name = sys.argv[1]

    try:

        team = find_team(team_name)

        if team is None:
            print(json.dumps({
                "success": False,
                "message": f"Could not find NBA team: {team_name}",
                "data": []
            }))
            return

        games = teams.team_game_log(team, "2025-26")

        result = {
            "success": True,
            "message": (
                f"Found {team['full_name']}. "
                f"Retrieved {len(games)} games."
            ),
            "team": {
                "id": team["id"],
                "name": team["full_name"],
                "abbreviation": team["abbreviation"],
                "city": team["city"],
                "nickname": team["nickname"]
            },
            "data": games
        }

        print(json.dumps(result))

    except Exception as e: # noqa: BLE001

        print(json.dumps({
            "success": False,
            "message": str(e),
            "data": []
        }))


if __name__ == "__main__":
    main()