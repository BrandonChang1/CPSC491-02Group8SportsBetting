import os

import pandas as pd
import psycopg
from dotenv import load_dotenv

from data.collection import espn as players
from data.collection import espn as teams
from data.collection.nba_game_logs import fetch_player_game_log
from data.processing.modeling_features import add_modeling_context

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

def recalculate_recent_minutes_avg() -> None:
    """
    Recalculate the five-game recent-minutes average
    for every stored player-game record.

    Only games before the current game are included,
    preventing data leakage.
    """

    database_url = get_database_url()

    query = """
        WITH rolling_minutes AS (
            SELECT
                pgs.player_id,
                pgs.game_id,
                AVG(pgs.minutes) OVER (
                    PARTITION BY pgs.player_id
                    ORDER BY
                        g.game_date,
                        pgs.game_id
                    ROWS BETWEEN 5 PRECEDING
                    AND 1 PRECEDING
                ) AS recent_minutes_avg
            FROM player_game_stats pgs
            JOIN games g
                ON pgs.game_id = g.id
        )
        UPDATE player_game_stats pgs
        SET recent_minutes_avg =
            rolling_minutes.recent_minutes_avg
        FROM rolling_minutes
        WHERE
            pgs.player_id =
                rolling_minutes.player_id
            AND pgs.game_id =
                rolling_minutes.game_id
    """

    with psycopg.connect(
        database_url,
        autocommit=True,
    ) as connection:
        connection.execute(query)

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

            except (psycopg.Error, KeyError, TypeError) as error:
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


# Latest recorded matchup is a historical roster estimate, not a live roster.
# Using the player's own abbreviation from MATCHUP also supports team changes.
TEAM_ID_BACKFILL_SQL = """
    WITH latest_team AS (
        SELECT DISTINCT ON (s.player_id)
            s.player_id,
            t.id AS team_id
        FROM player_game_stats s
        JOIN games g ON g.id = s.game_id
        JOIN teams t ON t.abbreviation =
            split_part(trim(s.matchup), ' ', 1)
        WHERE s.matchup IS NOT NULL
          AND (s.matchup LIKE '% vs. %' OR s.matchup LIKE '% @ %')
        ORDER BY s.player_id, g.game_date DESC, s.game_id DESC
    )
    UPDATE players p
    SET team_id = lt.team_id
    FROM latest_team lt
    WHERE p.id = lt.player_id
      AND p.team_id IS DISTINCT FROM lt.team_id
"""


def refresh_player_team_ids() -> int:
    """Assign historical teams from each player's latest stored matchup.

    This can update a player after a trade if newer game logs are ingested.
    It does not create teams or query live NBA rosters.
    """
    with psycopg.connect(get_database_url(), autocommit=True) as connection:
        result = connection.execute(TEAM_ID_BACKFILL_SQL)
        return result.rowcount


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
                        is_active,
                        team_id
                    )
                    VALUES (%s, %s, %s, %s, %s, (
                        SELECT t.id
                        FROM player_game_stats s
                        JOIN games g ON g.id = s.game_id
                        JOIN teams t ON t.abbreviation =
                            split_part(trim(s.matchup), ' ', 1)
                        WHERE s.player_id = %s
                          AND (s.matchup LIKE '%% vs. %%'
                               OR s.matchup LIKE '%% @ %%')
                        ORDER BY g.game_date DESC, s.game_id DESC
                        LIMIT 1
                    ))
                    ON CONFLICT (id)
                    DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        is_active = EXCLUDED.is_active,
                        team_id = COALESCE(EXCLUDED.team_id, players.team_id)
                    """,
                    (
                        player["id"],
                        player["full_name"],
                        player["first_name"],
                        player["last_name"],
                        player["is_active"],
                        player["id"],
                    ),
                )

                successful += 1

            except (psycopg.Error, KeyError, TypeError) as error:
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


def canonical_game_id(connection, row, team_ids):
    """Reuse NBA-era game IDs for the same date and home/away teams."""
    home, away = parse_matchup(row["matchup"])
    home_id, away_id = team_ids[home], team_ids[away]
    date = pd.Timestamp(row["game_date"]).date()
    matches = connection.execute(
        """SELECT id, game_date, home_team_id, away_team_id FROM games
           WHERE id = %s OR (game_date = %s AND home_team_id = %s AND away_team_id = %s)""",
        (row["game_id"], date, home_id, away_id),
    ).fetchall()
    if len(matches) > 1:
        raise ValueError("Ambiguous game mapping; reconcile existing duplicate games first")
    if not matches:
        return row["game_id"]
    game_id, stored_date, stored_home, stored_away = matches[0]
    if (stored_date, stored_home, stored_away) != (date, home_id, away_id):
        raise ValueError(f"Game identity mismatch: {game_id}")
    return game_id

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

                game_id = canonical_game_id(connection, row, team_ids)

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
                        game_id,
                        row["game_date"],
                        home_team_id,
                        away_team_id,
                    ),
                )

                successful += 1

            except (psycopg.Error, KeyError, TypeError, ValueError) as error:
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

def ingest_player_game_stats(game_logs) -> dict:
    """
    Insert cleaned player game-log rows into player_game_stats.

    Adds Sprint 3 modeling context:
        opponent_team_id
        is_home
        recent_minutes_avg

    Existing player/game rows are updated instead of duplicated.
    """

    processed = 0
    successful = 0
    failed = 0

    database_url = get_database_url()

    # Add opponent, home/away, and rolling recent-minutes context.
    contextualized_logs = add_modeling_context(game_logs)

    with psycopg.connect(
        database_url,
        autocommit=True,
    ) as connection:

        team_ids = get_team_id_map(connection)

        for _, row in contextualized_logs.iterrows():
            processed += 1

            try:
                opponent_team_id = team_ids.get(
                    row["opponent_abbreviation"]
                )

                if opponent_team_id is None:
                    raise ValueError(
                        "Unknown opponent team abbreviation: "
                        f"{row['opponent_abbreviation']}"
                    )

                game_id = canonical_game_id(connection, row, team_ids)

                # pandas represents the first unavailable rolling average
                # as NaN. Convert only that NaN value to SQL NULL.
                if pd.isna(row["recent_minutes_avg"]):
                    recent_minutes_avg = None
                else:
                    recent_minutes_avg = float(
                        row["recent_minutes_avg"]
                    )

                connection.execute(
                    """
                    INSERT INTO player_game_stats (
                        player_id,
                        game_id,
                        minutes,
                        points,
                        rebounds,
                        assists,
                        plus_minus,
                        matchup,
                        win_loss,
                        field_goals_made,
                        field_goals_attempted,
                        field_goal_pct,
                        three_pointers_made,
                        three_pointers_attempted,
                        three_point_pct,
                        free_throws_made,
                        free_throws_attempted,
                        free_throw_pct,
                        offensive_rebounds,
                        defensive_rebounds,
                        steals,
                        blocks,
                        turnovers,
                        personal_fouls,
                        opponent_team_id,
                        is_home,
                        recent_minutes_avg
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (player_id, game_id)
                    DO UPDATE SET
                        minutes = EXCLUDED.minutes,
                        points = EXCLUDED.points,
                        rebounds = EXCLUDED.rebounds,
                        assists = EXCLUDED.assists,
                        plus_minus = EXCLUDED.plus_minus,
                        matchup = EXCLUDED.matchup,
                        win_loss = EXCLUDED.win_loss,
                        field_goals_made =
                            EXCLUDED.field_goals_made,
                        field_goals_attempted =
                            EXCLUDED.field_goals_attempted,
                        field_goal_pct =
                            EXCLUDED.field_goal_pct,
                        three_pointers_made =
                            EXCLUDED.three_pointers_made,
                        three_pointers_attempted =
                            EXCLUDED.three_pointers_attempted,
                        three_point_pct =
                            EXCLUDED.three_point_pct,
                        free_throws_made =
                            EXCLUDED.free_throws_made,
                        free_throws_attempted =
                            EXCLUDED.free_throws_attempted,
                        free_throw_pct =
                            EXCLUDED.free_throw_pct,
                        offensive_rebounds =
                            EXCLUDED.offensive_rebounds,
                        defensive_rebounds =
                            EXCLUDED.defensive_rebounds,
                        steals =
                            EXCLUDED.steals,
                        blocks =
                            EXCLUDED.blocks,
                        turnovers =
                            EXCLUDED.turnovers,
                        personal_fouls =
                            EXCLUDED.personal_fouls,
                        opponent_team_id =
                            EXCLUDED.opponent_team_id,
                        is_home =
                            EXCLUDED.is_home,
                        recent_minutes_avg =
                            EXCLUDED.recent_minutes_avg
                    """,
                    (
                        row["player_id"],
                        game_id,
                        row["minutes"],
                        row["points"],
                        row["rebounds"],
                        row["assists"],
                        row["plus_minus"],
                        row["matchup"],
                        row["win_loss"],
                        row["field_goals_made"],
                        row["field_goals_attempted"],
                        row["field_goal_pct"],
                        row["three_pointers_made"],
                        row["three_pointers_attempted"],
                        row["three_point_pct"],
                        row["free_throws_made"],
                        row["free_throws_attempted"],
                        row["free_throw_pct"],
                        row["offensive_rebounds"],
                        row["defensive_rebounds"],
                        row["steals"],
                        row["blocks"],
                        row["turnovers"],
                        row["personal_fouls"],
                        opponent_team_id,
                        bool(row["is_home"]),
                        recent_minutes_avg,
                    ),
                )

                successful += 1

            except (
                psycopg.Error,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                failed += 1

                print(
                    "Failed to ingest player game stats "
                    f"for game "
                    f"{row.get('game_id', 'unknown')}: "
                    f"{error}"
                )

    # Refresh recorded team associations after stats have been inserted.
    # Do not silently swallow a database error: ingestion should report it.
    if successful:
        refresh_player_team_ids()

    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
    }

def main():
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

    stats_results = ingest_player_game_stats(
        curry_game_logs
    )

    print(
        "Player game stats:",
        f"processed={stats_results['processed']}",
        f"successful={stats_results['successful']}",
        f"failed={stats_results['failed']}",
    )

    print("NBA database ingestion complete.")


if __name__ == "__main__":
    main()
