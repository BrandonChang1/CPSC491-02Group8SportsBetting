import time

import psycopg
from nba_api.stats.static import players

from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion.database_ingestion import (
    get_database_url,
    ingest_games,
    ingest_player_game_stats,
    ingest_players,
    ingest_teams,
    recalculate_recent_minutes_avg,
)

TARGET_STAT_ROWS = 5000

SEASONS = [
    "2024-25",
]


def get_player_game_stat_count() -> int:
    """
    Return the current number of player-game observations.
    """

    database_url = get_database_url()

    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM player_game_stats
            """
        ).fetchone()

    return row[0]


def main():
    print("Starting historical NBA backfill...")
    print(
        f"Target: {TARGET_STAT_ROWS} "
        "player-game observations"
    )

    team_results = ingest_teams()
    player_results = ingest_players()

    print(
        "Teams:",
        f"successful={team_results['successful']}",
        f"failed={team_results['failed']}",
    )

    print(
        "Players:",
        f"successful={player_results['successful']}",
        f"failed={player_results['failed']}",
    )

    active_players = players.get_active_players()

    current_count = get_player_game_stat_count()

    print(
        f"Starting database row count: "
        f"{current_count}"
    )

    processed_players = 0
    failures = 0

    for player in active_players:
        if current_count >= TARGET_STAT_ROWS:
            break

        player_id = player["id"]
        player_name = player["full_name"]

        print(
            f"\nProcessing {player_name} "
            f"({player_id})"
        )

        for season in SEASONS:
            try:
                print(
                    f"Fetching {season} game logs..."
                )

                game_logs = fetch_player_game_log(
                    player_id=player_id,
                    season=season,
                )

                if game_logs.empty:
                    print(
                        "No game logs returned."
                    )
                    continue

                game_results = ingest_games(
                    game_logs
                )

                stat_results = (
                    ingest_player_game_stats(
                        game_logs
                    )
                )

                print(
                    f"{season}: "
                    f"games={game_results['successful']} "
                    f"stats={stat_results['successful']} "
                    f"failed={stat_results['failed']}"
                )

                time.sleep(1)

            except (
                ValueError,
                KeyError,
                TypeError,
                psycopg.Error,
            ) as error:
                failures += 1

                print(
                    f"Failed to process "
                    f"{player_name} "
                    f"for {season}: {error}"
                )

        processed_players += 1

        current_count = (
            get_player_game_stat_count()
        )

        print(
            f"Database now contains "
            f"{current_count} "
            "player-game observations."
        )

    print(
        "\nRecalculating recent_minutes_avg "
        "from complete historical data..."
    )

    recalculate_recent_minutes_avg()

    final_count = get_player_game_stat_count()

    print("\nHistorical backfill complete.")

    print(
        f"Players processed: "
        f"{processed_players}"
    )

    print(
        f"Player-game observations: "
        f"{final_count}"
    )

    print(
        f"Failures: {failures}"
    )

    if final_count >= TARGET_STAT_ROWS:
        print(
            f"Target of {TARGET_STAT_ROWS} "
            "observations reached."
        )
    else:
        print(
            f"Target not reached. "
            f"Current total: {final_count}"
        )


if __name__ == "__main__":
    main()