import sys
import json

from nba_api.stats.static import teams
from nba_api.stats.endpoints import teamgamelog


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

        team_id = team["id"]

        game_log = teamgamelog.TeamGameLog(
            team_id=team_id,
            season="2025-26"
        )

        df = game_log.get_data_frames()[0]

        columns_to_return = [
            "GAME_DATE",
            "MATCHUP",
            "WL",
            "W",
            "L",
            "PTS",
            "REB",
            "AST"
        ]

        # Keep only columns that actually exist
        available_columns = [
            column
            for column in columns_to_return
            if column in df.columns
        ]

        df = df[available_columns]

        # Limit output for testing
        df = df.head(10)

        result = {
            "success": True,
            "message": (
                f"Found {team['full_name']}. "
                f"Retrieved {len(df)} games."
            ),
            "team": {
                "id": team["id"],
                "name": team["full_name"],
                "abbreviation": team["abbreviation"],
                "city": team["city"],
                "nickname": team["nickname"]
            },
            "data": df.to_dict(orient="records")
        }

        print(json.dumps(result))

    except Exception as e:

        print(json.dumps({
            "success": False,
            "message": str(e),
            "data": []
        }))


if __name__ == "__main__":
    main()