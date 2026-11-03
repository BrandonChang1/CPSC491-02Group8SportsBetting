"""Manual ESPN smoke check (kept at the old path for existing commands)."""
from data.collection.espn import get_players, get_teams
from data.collection.nba_game_logs import fetch_player_game_log


def main():
    print("ESPN teams:", len(get_teams()))
    print("ESPN players:", len(get_players()))
    print(fetch_player_game_log(201939, "2025-26").head())


if __name__ == "__main__":
    main()
