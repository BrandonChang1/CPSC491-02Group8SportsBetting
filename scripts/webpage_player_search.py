import sys
import json

import pandas as pd
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog


DEFAULT_SEASON = "2025-26"
MAX_SEARCH_RESULTS = 10
RECENT_GAME_COUNT = 10


def search_players(search_term):
    """Return up to 10 NBA players whose names match the search term."""
    search_term = search_term.strip().lower()

    if not search_term:
        return []

    matches = []

    for player in players.get_players():
        full_name = player["full_name"]
        lower_name = full_name.lower()

        if search_term in lower_name:
            matches.append({
                "id": player["id"],
                "name": full_name,
                "is_active": player["is_active"],
                # Used only for sorting; removed before returning.
                "starts_with_search": lower_name.startswith(search_term),
            })

    # Prefer active players, then names that start with the search text,
    # then alphabetical order.
    matches.sort(
        key=lambda player: (
            not player["is_active"],
            not player["starts_with_search"],
            player["name"],
        )
    )

    results = []

    for player in matches[:MAX_SEARCH_RESULTS]:
        results.append({
            "id": player["id"],
            "name": player["name"],
            "is_active": player["is_active"],
        })

    return results


def get_recent_games(player_id, season=DEFAULT_SEASON):
    """Return the player's 10 most recent games and averages for those games."""
    game_log = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=season,
        season_type_all_star="Regular Season",
    )

    df = game_log.get_data_frames()[0].copy()

    if df.empty:
        return [], {}

    # Convert the NBA API date to a real date so the newest games are first.
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df = df.sort_values("GAME_DATE", ascending=False).head(RECENT_GAME_COUNT)

    numeric_columns = ["MIN", "PTS", "REB", "AST", "PLUS_MINUS"]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    display_columns = [
        "GAME_DATE",
        "MATCHUP",
        "WL",
        "MIN",
        "PTS",
        "REB",
        "AST",
        "PLUS_MINUS",
    ]

    available_columns = [
        column for column in display_columns if column in df.columns
    ]

    recent_df = df[available_columns].copy()

    if "GAME_DATE" in recent_df.columns:
        recent_df["GAME_DATE"] = recent_df["GAME_DATE"].dt.strftime("%Y-%m-%d")

    averages = {}
    average_labels = {
        "MIN": "minutes",
        "PTS": "points",
        "REB": "rebounds",
        "AST": "assists",
        "PLUS_MINUS": "plus_minus",
    }

    for column, output_name in average_labels.items():
        if column in df.columns:
            average = df[column].mean()
            averages[output_name] = (
                None if pd.isna(average) else round(float(average), 1)
            )

    return recent_df.to_dict(orient="records"), averages


def print_json(payload):
    print(json.dumps(payload))


def main():
    if len(sys.argv) < 3:
        print_json({
            "success": False,
            "message": "Usage: webpage_player_search.py search <name> OR stats <player_id>",
            "data": [],
        })
        return

    mode = sys.argv[1].lower()
    value = sys.argv[2]

    try:
        if mode == "search":
            matches = search_players(value)

            print_json({
                "success": True,
                "message": f"Found {len(matches)} matching players.",
                "data": matches,
            })
            return

        if mode == "stats":
            try:
                player_id = int(value)
            except ValueError:
                print_json({
                    "success": False,
                    "message": "Player ID must be a number.",
                    "data": [],
                })
                return

            player = players.find_player_by_id(player_id)

            if player is None:
                print_json({
                    "success": False,
                    "message": f"Could not find player ID {player_id}.",
                    "data": [],
                })
                return

            games, averages = get_recent_games(player_id)

            print_json({
                "success": True,
                "message": f"Loaded {len(games)} recent games for {player['full_name']}.",
                "player": {
                    "id": player["id"],
                    "name": player["full_name"],
                    "is_active": player["is_active"],
                },
                "season": DEFAULT_SEASON,
                "averages": averages,
                "data": games,
            })
            return

        print_json({
            "success": False,
            "message": f"Unknown mode: {mode}",
            "data": [],
        })

    except Exception as error:
        print_json({
            "success": False,
            "message": str(error),
            "data": [],
        })


if __name__ == "__main__":
    main()
