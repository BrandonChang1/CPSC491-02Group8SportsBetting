# test_nba_api.py

from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog


def test_nba_api():
    print("=== NBA API Connection Test ===\n")

    try:
        # ---------------------------------------------------------
        # 1. Find a player
        # ---------------------------------------------------------
        player_name = "Stephen Curry"

        matches = players.find_players_by_full_name(player_name)

        if not matches:
            print(f"[FAIL] Could not find player: {player_name}")
            return

        player = matches[0]
        player_id = player["id"]

        print("[PASS] Player lookup successful")
        print(f"Player: {player['full_name']}")
        print(f"NBA Player ID: {player_id}\n")

        # ---------------------------------------------------------
        # 2. Request game logs
        # ---------------------------------------------------------
        print("Requesting game log data...")

        game_log = playergamelog.PlayerGameLog(
            player_id=player_id,
            season="2024-25",
            season_type_all_star="Regular Season",
            timeout=30
        )

        # nba_api endpoints normally return Pandas DataFrames
        df = game_log.get_data_frames()[0]

        # ---------------------------------------------------------
        # 3. Validate response
        # ---------------------------------------------------------
        if df.empty:
            print("[FAIL] API request succeeded, but no game data was returned.")
            return

        print("[PASS] Game log retrieved successfully")
        print(f"Rows returned: {len(df)}")
        print(f"Columns returned: {len(df.columns)}\n")

        # ---------------------------------------------------------
        # 4. Display columns
        # ---------------------------------------------------------
        print("Columns:")
        print(list(df.columns))
        print()

        # ---------------------------------------------------------
        # 5. Display a few useful stats
        # ---------------------------------------------------------
        wanted_columns = [
            "GAME_DATE",
            "MATCHUP",
            "MIN",
            "PTS",
            "REB",
            "AST",
            "FG_PCT",
            "FG3_PCT"
        ]

        available_columns = [
            column
            for column in wanted_columns
            if column in df.columns
        ]

        print("First 5 games:")
        print(df[available_columns].head())

        print("\n=== TEST PASSED ===")

    except Exception as error:
        print("\n=== TEST FAILED ===")
        print(f"Error type: {type(error).__name__}")
        print(f"Error: {error}")


if __name__ == "__main__":
    test_nba_api()