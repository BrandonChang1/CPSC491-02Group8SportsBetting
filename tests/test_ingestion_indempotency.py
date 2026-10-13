import os

import pandas as pd
import psycopg
import pytest
from dotenv import load_dotenv

from data.ingestion.database_ingestion import (
    ingest_games,
    ingest_player_game_stats,
)

load_dotenv()


TEST_PLAYER_ID = 999999001
TEST_HOME_TEAM_ID = 999999101
TEST_AWAY_TEAM_ID = 999999102
TEST_GAME_ID = "TEST640001"


@pytest.fixture
def database_url():
    url = os.getenv("DATABASE_URL")

    if not url:
        pytest.fail(
            "DATABASE_URL is not set. "
            "Idempotency tests require the test database."
        )

    return url


@pytest.fixture
def controlled_game_logs(database_url):
    """
    Create the minimum related records required for a
    controlled player-game ingestion test.

    All synthetic records are deleted after the test.
    """

    with psycopg.connect(
        database_url,
        autocommit=True,
    ) as connection:
        connection.execute(
            """
            INSERT INTO teams (
                id,
                full_name,
                abbreviation,
                city
            )
            VALUES
                (
                    %s,
                    'SCRUM 64 Home Team',
                    'T64H',
                    'Test City'
                ),
                (
                    %s,
                    'SCRUM 64 Away Team',
                    'T64A',
                    'Test City'
                )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                TEST_HOME_TEAM_ID,
                TEST_AWAY_TEAM_ID,
            ),
        )

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
            VALUES (
                %s,
                'SCRUM 64 Test Player',
                'SCRUM',
                'Player',
                TRUE,
                %s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                TEST_PLAYER_ID,
                TEST_HOME_TEAM_ID,
            ),
        )

    game_logs = pd.DataFrame(
        [
            {
                "player_id": TEST_PLAYER_ID,
                "game_id": TEST_GAME_ID,
                "game_date": pd.Timestamp("2025-01-01"),
                "matchup": "T64H vs. T64A",
                "win_loss": "W",
                "minutes": 30,
                "field_goals_made": 8,
                "field_goals_attempted": 15,
                "field_goal_pct": 0.533,
                "three_pointers_made": 3,
                "three_pointers_attempted": 7,
                "three_point_pct": 0.429,
                "free_throws_made": 4,
                "free_throws_attempted": 4,
                "free_throw_pct": 1.0,
                "offensive_rebounds": 1,
                "defensive_rebounds": 4,
                "rebounds": 5,
                "assists": 7,
                "steals": 2,
                "blocks": 0,
                "turnovers": 2,
                "personal_fouls": 1,
                "points": 23,
                "plus_minus": 6,
            }
        ]
    )

    yield game_logs

    with psycopg.connect(
        database_url,
        autocommit=True,
    ) as connection:
        connection.execute(
            """
            DELETE FROM player_game_stats
            WHERE player_id = %s
            """,
            (TEST_PLAYER_ID,),
        )

        connection.execute(
            """
            DELETE FROM games
            WHERE id = %s
            """,
            (TEST_GAME_ID,),
        )

        connection.execute(
            """
            DELETE FROM players
            WHERE id = %s
            """,
            (TEST_PLAYER_ID,),
        )

        connection.execute(
            """
            DELETE FROM teams
            WHERE id IN (%s, %s)
            """,
            (
                TEST_HOME_TEAM_ID,
                TEST_AWAY_TEAM_ID,
            ),
        )


def get_game_count(database_url):
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM games
            WHERE id = %s
            """,
            (TEST_GAME_ID,),
        ).fetchone()[0]


def get_player_game_count(database_url):
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            """
            SELECT COUNT(*)
            FROM player_game_stats
            WHERE
                player_id = %s
                AND game_id = %s
            """,
            (
                TEST_PLAYER_ID,
                TEST_GAME_ID,
            ),
        ).fetchone()[0]


def get_stored_values(database_url):
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            """
            SELECT
                minutes,
                points,
                rebounds,
                assists,
                plus_minus,
                opponent_team_id,
                is_home
            FROM player_game_stats
            WHERE
                player_id = %s
                AND game_id = %s
            """,
            (
                TEST_PLAYER_ID,
                TEST_GAME_ID,
            ),
        ).fetchone()


def test_repeated_ingestion_is_idempotent(
    database_url,
    controlled_game_logs,
):
    """
    Ingesting the same source records twice must not
    create additional unique games or player-game rows.
    """

    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)

    first_game_count = get_game_count(database_url)
    first_stat_count = get_player_game_count(
        database_url
    )
    first_values = get_stored_values(database_url)

    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)

    second_game_count = get_game_count(database_url)
    second_stat_count = get_player_game_count(
        database_url
    )
    second_values = get_stored_values(database_url)

    assert first_game_count == 1
    assert second_game_count == 1

    assert first_stat_count == 1
    assert second_stat_count == 1

    assert second_values == first_values


def test_duplicate_player_game_records_remain_zero(
    database_url,
    controlled_game_logs,
):
    """
    Reprocessing the same record must not create duplicate
    (player_id, game_id) combinations.
    """

    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)

    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)

    with psycopg.connect(database_url) as connection:
        duplicates = connection.execute(
            """
            SELECT
                player_id,
                game_id,
                COUNT(*)
            FROM player_game_stats
            WHERE player_id = %s
            GROUP BY
                player_id,
                game_id
            HAVING COUNT(*) > 1
            """,
            (TEST_PLAYER_ID,),
        ).fetchall()

    assert duplicates == []