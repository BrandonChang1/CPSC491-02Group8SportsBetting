import os

import psycopg
from dotenv import load_dotenv
from nba_api.stats.static import players, teams
from data.collection.nba_game_logs import fetch_player_game_log

load_dotenv()
def get_database_url() -> str:
    """
    Return the PostgreSQL connection string from the environment.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Load your .env file before running database ingestion."
        )

    return database_url


def ingest_teams() -> dict:
    """
    Retrieve NBA teams and insert them into PostgreSQL.

    Existing team records are updated instead of duplicated.

    Returns:
        Dictionary containing processed, successful, and failed counts.
    """

    nba_teams = teams.get_teams()

    processed = 0
    successful = 0
    failed = 0

    database_url = get_database_url()

    with psycopg.connect(database_url, autocommit=True) as connection:
        for team in nba_teams:
            processed += 1

            try:
                connection.execute(
                    """
                    INSERT INTO teams (
                        id,
                        full_name,
                        abbreviation,
                        city
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        abbreviation = EXCLUDED.abbreviation,
                        city = EXCLUDED.city
                    """,
                    (
                        team["id"],
                        team["full_name"],
                        team["abbreviation"],
                        team["city"],
                    ),
                )

                successful += 1

            except Exception as error:
                failed += 1

                print(
                    f"Failed to ingest team "
                    f"{team.get('full_name', 'unknown')}: {error}"
                )

    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
    }


def ingest_players() -> dict:
    """
    Retrieve NBA players and insert them into PostgreSQL.

    Existing player records are updated instead of duplicated.

    Returns:
        Dictionary containing processed, successful, and failed counts.
    """

    nba_players = players.get_players()

    processed = 0
    successful = 0
    failed = 0

    database_url = get_database_url()

    with psycopg.connect(database_url, autocommit=True) as connection:
        for player in nba_players:
            processed += 1

            try:
                connection.execute(
                    """
                    INSERT INTO players (
                        id,
                        full_name,
                        first_name,
                        last_name,
                        is_active
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        player["id"],
                        player["full_name"],
                        player["first_name"],
                        player["last_name"],
                        player["is_active"],
                    ),
                )

                successful += 1

            except Exception as error:
                failed += 1

                print(
                    f"Failed to ingest player "
                    f"{player.get('full_name', 'unknown')}: {error}"
                )

    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
    }

def parse_matchup(matchup: str) -> tuple[str, str]:
    """
    Parse an NBA matchup string and return:

        (home_team_abbreviation, away_team_abbreviation)

    Examples:
        "GSW vs. LAL" -> ("GSW", "LAL")
        "GSW @ POR"   -> ("POR", "GSW")
    """

    if " vs. " in matchup:
        team_abbreviation, opponent_abbreviation = matchup.split(" vs. ")

        return (
            team_abbreviation.strip(),
            opponent_abbreviation.strip(),
        )

    if " @ " in matchup:
        team_abbreviation, opponent_abbreviation = matchup.split(" @ ")

        return (
            opponent_abbreviation.strip(),
            team_abbreviation.strip(),
        )

    raise ValueError(f"Unrecognized matchup format: {matchup}")

def get_team_id_map(connection) -> dict:
    """
    Return a mapping of NBA team abbreviations to database team IDs.
    """

    rows = connection.execute(
        """
        SELECT id, abbreviation
        FROM teams
        """
    ).fetchall()

    return {
        abbreviation: team_id
        for team_id, abbreviation in rows
    }

def ingest_games(game_logs) -> dict:
    """
    Insert games from a cleaned player game-log DataFrame.

    Duplicate games are updated instead of inserted again.
    Failed rows are logged without stopping the rest of the ingestion.

    Args:
        game_logs: Cleaned pandas DataFrame returned by
                   fetch_player_game_log().

    Returns:
        Dictionary containing processed, successful, and failed counts.
    """

    processed = 0
    successful = 0
    failed = 0

    database_url = get_database_url()

    with psycopg.connect(
        database_url,
        autocommit=True,
    ) as connection:

        team_ids = get_team_id_map(connection)

        for _, row in game_logs.iterrows():
            processed += 1

            try:
                home_abbreviation, away_abbreviation = parse_matchup(
                    row["matchup"]
                )

                home_team_id = team_ids.get(home_abbreviation)
                away_team_id = team_ids.get(away_abbreviation)

                if home_team_id is None:
                    raise ValueError(
                        f"Unknown home team abbreviation: "
                        f"{home_abbreviation}"
                    )

                if away_team_id is None:
                    raise ValueError(
                        f"Unknown away team abbreviation: "
                        f"{away_abbreviation}"
                    )

                connection.execute(
                    """
                    INSERT INTO games (
                        id,
                        game_date,
                        home_team_id,
                        away_team_id
                    )
                    VALUES (%s, %s, %s, %s)

                    ON CONFLICT (id)
                    DO UPDATE SET
                        game_date = EXCLUDED.game_date,
                        home_team_id = EXCLUDED.home_team_id,
                        away_team_id = EXCLUDED.away_team_id
                    """,
                    (
                        row["game_id"],
                        row["game_date"],
                        home_team_id,
                        away_team_id,
                    ),
                )

                successful += 1

            except Exception as error:
                failed += 1

                print(
                    f"Failed to ingest game "
                    f"{row.get('game_id', 'unknown')}: {error}"
                )

    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
    }

def main():
    curry = players.find_players_by_full_name(
        "Stephen Curry"
    )[0]

    curry_game_logs = fetch_player_game_log(
        player_id=curry["id"],
        season="2025-26",
    )

    game_results = ingest_games(curry_game_logs)

    print(
        "Games:",
        f"processed={game_results['processed']}",
        f"successful={game_results['successful']}",
        f"failed={game_results['failed']}",
    )
    print("Starting NBA database ingestion...")

    team_results = ingest_teams()

    print(
        "Teams:",
        f"processed={team_results['processed']}",
        f"successful={team_results['successful']}",
        f"failed={team_results['failed']}",
    )

    player_results = ingest_players()

    print(
        "Players:",
        f"processed={player_results['processed']}",
        f"successful={player_results['successful']}",
        f"failed={player_results['failed']}",
    )

    print("NBA database ingestion complete.")


if __name__ == "__main__":
    main()