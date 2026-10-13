from pathlib import Path

import pandas as pd
import psycopg

from data.ingestion.database_ingestion import get_database_url


OUTPUT_PATH = Path(
    "data/sample/player_game_stats_sample.csv"
)


def export_player_game_stats() -> Path:
    """
    Export stored player-game observations to CSV
    for ML development and testing.
    """

    database_url = get_database_url()

    query = """
        SELECT
            pgs.player_id,
            p.full_name AS player_name,
            pgs.game_id,
            g.game_date,
            pgs.matchup,
            pgs.win_loss,
            pgs.minutes,
            pgs.points,
            pgs.rebounds,
            pgs.assists,
            pgs.plus_minus,
            pgs.field_goals_made,
            pgs.field_goals_attempted,
            pgs.field_goal_pct,
            pgs.three_pointers_made,
            pgs.three_pointers_attempted,
            pgs.three_point_pct,
            pgs.free_throws_made,
            pgs.free_throws_attempted,
            pgs.free_throw_pct,
            pgs.offensive_rebounds,
            pgs.defensive_rebounds,
            pgs.steals,
            pgs.blocks,
            pgs.turnovers,
            pgs.personal_fouls,
            pgs.opponent_team_id,
            opponent.abbreviation AS opponent,
            pgs.is_home,
            pgs.recent_minutes_avg
        FROM player_game_stats pgs
        JOIN players p
            ON pgs.player_id = p.id
        JOIN games g
            ON pgs.game_id = g.id
        LEFT JOIN teams opponent
            ON pgs.opponent_team_id = opponent.id
        ORDER BY
            pgs.player_id,
            g.game_date,
            pgs.game_id
    """

    with psycopg.connect(database_url) as connection:
        cursor = connection.execute(query)

        rows = cursor.fetchall()

        column_names = [
            description.name
            for description in cursor.description
        ]

    dataset = pd.DataFrame(
        rows,
        columns=column_names,
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset.to_csv(
        OUTPUT_PATH,
        index=False,
        lineterminator="\n",
    )

    print(
        f"Exported {len(dataset)} "
        "player-game observations."
    )

    print(
        f"Players: "
        f"{dataset['player_id'].nunique()}"
    )

    print(
        f"Games: "
        f"{dataset['game_id'].nunique()}"
    )

    print(
        f"CSV saved to: {OUTPUT_PATH}"
    )

    return OUTPUT_PATH


def main():
    export_player_game_stats()


if __name__ == "__main__":
    main()