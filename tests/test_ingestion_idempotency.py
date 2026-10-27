import os
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from dotenv import load_dotenv

from data.ingestion import database_ingestion as ingestion
from data.ingestion.database_ingestion import (
    ingest_games,
    ingest_player_game_stats,
)

load_dotenv()


TEST_PLAYER_ID = 999999001
TEST_HOME_TEAM_ID = 999999101
TEST_AWAY_TEAM_ID = 999999102
TEST_GAME_ID = "TEST640001"


def test_roster_teams_override_history_and_survive_backfill(database_url, monkeypatch):
    # Temporary tables keep this regression isolated from stored player data.
    with psycopg.connect(database_url) as connection:
        schema = Path("database/schema.sql").read_text()
        connection.execute(schema.replace("CREATE TABLE", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO teams (id, full_name, abbreviation)
            VALUES (1, 'Old Team', 'OLD'), (2, 'New Team', 'NEW');
            INSERT INTO players (id, full_name, is_active)
            VALUES (101, 'Historical Player', FALSE);
            INSERT INTO games (id, game_date, home_team_id, away_team_id)
            VALUES ('roster-test', '2025-01-01', 1, 2);
            INSERT INTO player_game_stats (player_id, game_id, matchup)
            VALUES (101, 'roster-test', 'OLD vs. NEW');
        """)
        roster = [{
            "id": 100, "full_name": "Roster Player", "first_name": "Roster",
            "last_name": "Player", "is_active": True, "team_id": 1,
        }]
        with monkeypatch.context() as patch:
            patch.setattr(ingestion.players, "get_players", lambda: roster)
            patch.setattr(ingestion.psycopg, "connect", lambda *a, **kw: nullcontext(connection))
            assert ingestion.ingest_players() == {"processed": 1, "successful": 1, "failed": 0}
            assert connection.execute("SELECT team_id FROM players WHERE id=100").fetchone() == (1,)
            connection.execute("""
                INSERT INTO player_game_stats (player_id, game_id, matchup)
                VALUES (100, 'roster-test', 'OLD vs. NEW')
            """)
            roster[0]["team_id"] = 2
            for _ in range(2):
                assert ingestion.ingest_players()["successful"] == 1
                ingestion.refresh_player_team_ids()
                assert connection.execute("SELECT team_id FROM players ORDER BY id").fetchall() == [(2,), (1,)]
            migration = Path("database/migrations/004_backfill_player_team_ids.sql").read_text()
            connection.execute(migration)
            assert connection.execute("SELECT team_id FROM players WHERE id=100").fetchone() == (2,)


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

def test_espn_reingestion_reuses_legacy_game_id(database_url, controlled_game_logs):
    """Switching providers must retain the original game and player-stat identity."""
    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)
    before = get_stored_values(database_url)
    espn_logs = controlled_game_logs.copy()
    espn_logs["game_id"] = "espn:401999999"

    for _ in range(2):
        assert ingest_games(espn_logs)["failed"] == 0
        assert ingest_player_game_stats(espn_logs)["failed"] == 0

    assert get_game_count(database_url) == 1
    assert get_player_game_count(database_url) == 1
    assert get_stored_values(database_url) == before
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT COUNT(*) FROM games WHERE id = %s", ("espn:401999999",)).fetchone()[0] == 0


def test_game_identity_mismatch_does_not_overwrite_history(database_url, controlled_game_logs):
    ingest_games(controlled_game_logs)
    ingest_player_game_stats(controlled_game_logs)
    before = get_stored_values(database_url)
    wrong_date = controlled_game_logs.copy()
    wrong_date["game_date"] = pd.Timestamp("2025-01-02")
    assert ingest_games(wrong_date)["failed"] == 1
    assert ingest_player_game_stats(wrong_date)["failed"] == 1
    assert get_stored_values(database_url) == before
    with psycopg.connect(database_url) as connection:
        assert str(connection.execute("SELECT game_date FROM games WHERE id = %s", (TEST_GAME_ID,)).fetchone()[0]) == "2025-01-01"


def test_full_espn_response_reuses_legacy_database_record(database_url, controlled_game_logs, espn_responses):
    from data.collection.nba_game_logs import fetch_player_game_log

    assert ingest_games(controlled_game_logs)["failed"] == 0
    logs = fetch_player_game_log(201939, "2024-25").assign(
        player_id=TEST_PLAYER_ID,
        game_date=pd.Timestamp("2025-01-01"),
        matchup="T64H vs. T64A",
    )
    for _ in range(2):
        assert ingest_games(logs)["failed"] == 0
        assert ingest_player_game_stats(logs)["failed"] == 0
    assert get_game_count(database_url) == 1
    assert get_player_game_count(database_url) == 1
    values = get_stored_values(database_url)
    assert values[:4] == (38, 36, 3, 6)
    assert values[5:] == (TEST_AWAY_TEAM_ID, True)
