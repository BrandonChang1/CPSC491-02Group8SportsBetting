from pathlib import Path

from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog

from scripts.clean_nba_data import clean_player_game_log


def main():
    curry = players.find_players_by_full_name("Stephen Curry")[0]

    game_log = playergamelog.PlayerGameLog(
        player_id=curry["id"],
        season="2025-26",
        season_type_all_star="Regular Season",
    )

    raw_df = game_log.get_data_frames()[0]

    if raw_df.empty:
        print("No game log data was returned.")
        return

    clean_df = clean_player_game_log(raw_df)

    if clean_df.empty:
        print("No cleaned game log data is available.")
        return

    output_dir = Path("data/sample")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "sample_player_game_logs.csv"

    clean_df.to_csv(output_path, index=False)

    print(f"Saved {len(clean_df)} rows to {output_path}")


if __name__ == "__main__":
    main()