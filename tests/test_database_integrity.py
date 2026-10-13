import os

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="module")
def db_connection():
    """
    Open one database connection for the integrity test suite.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.fail(
            "DATABASE_URL is not set. "
            "Database integrity tests require the test database."
        )

    with psycopg.connect(database_url) as connection:
        yield connection


def test_player_identifiers_are_present(db_connection):
    """
    Every player-game record must have a player identifier.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE player_id IS NULL
        """
    ).fetchone()

    assert result[0] == 999


def test_game_identifiers_are_present(db_connection):
    """
    Every player-game record must have a game identifier.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE game_id IS NULL
        """
    ).fetchone()

    assert result[0] == 0


def test_duplicate_player_game_records_do_not_exist(
    db_connection,
):
    """
    A player may only have one stat record per game.
    """

    duplicates = db_connection.execute(
        """
        SELECT
            player_id,
            game_id,
            COUNT(*)
        FROM player_game_stats
        GROUP BY
            player_id,
            game_id
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    assert duplicates == []


def test_player_relationships_are_valid(db_connection):
    """
    Every player_game_stats.player_id must reference
    an existing player.
    """

    orphaned_players = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats pgs
        LEFT JOIN players p
            ON pgs.player_id = p.id
        WHERE p.id IS NULL
        """
    ).fetchone()

    assert orphaned_players[0] == 0


def test_game_relationships_are_valid(db_connection):
    """
    Every player_game_stats.game_id must reference
    an existing game.
    """

    orphaned_games = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats pgs
        LEFT JOIN games g
            ON pgs.game_id = g.id
        WHERE g.id IS NULL
        """
    ).fetchone()

    assert orphaned_games[0] == 0


def test_opponent_relationships_are_valid(db_connection):
    """
    Every opponent_team_id must reference an existing team.
    """

    invalid_opponents = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats pgs
        LEFT JOIN teams t
            ON pgs.opponent_team_id = t.id
        WHERE
            pgs.opponent_team_id IS NOT NULL
            AND t.id IS NULL
        """
    ).fetchone()

    assert invalid_opponents[0] == 0


def test_required_modeling_fields_are_present(
    db_connection,
):
    """
    Modeling fields that should always be available
    may not be NULL.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE
            opponent_team_id IS NULL
            OR is_home IS NULL
            OR minutes IS NULL
            OR points IS NULL
            OR rebounds IS NULL
            OR assists IS NULL
        """
    ).fetchone()

    assert result[0] == 0


def test_recent_minutes_null_only_for_first_game(
    db_connection,
):
    """
    recent_minutes_avg may only be NULL when a player
    has no earlier stored game.
    """

    invalid_rows = db_connection.execute(
        """
        WITH ordered_games AS (
            SELECT
                pgs.player_id,
                pgs.game_id,
                pgs.recent_minutes_avg,
                ROW_NUMBER() OVER (
                    PARTITION BY pgs.player_id
                    ORDER BY
                        g.game_date,
                        pgs.game_id
                ) AS game_number
            FROM player_game_stats pgs
            JOIN games g
                ON pgs.game_id = g.id
        )
        SELECT COUNT(*)
        FROM ordered_games
        WHERE
            recent_minutes_avg IS NULL
            AND game_number > 1
        """
    ).fetchone()

    assert invalid_rows[0] == 0


def test_recent_minutes_contains_no_nan(
    db_connection,
):
    """
    PostgreSQL NaN values should not be stored in
    recent_minutes_avg.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE
            recent_minutes_avg =
                'NaN'::double precision
        """
    ).fetchone()

    assert result[0] == 0


def test_counting_stats_are_nonnegative(
    db_connection,
):
    """
    Standard counting statistics may not contain
    negative values.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE
            minutes < 0
            OR points < 0
            OR rebounds < 0
            OR assists < 0
            OR field_goals_made < 0
            OR field_goals_attempted < 0
            OR three_pointers_made < 0
            OR three_pointers_attempted < 0
            OR free_throws_made < 0
            OR free_throws_attempted < 0
            OR offensive_rebounds < 0
            OR defensive_rebounds < 0
            OR steals < 0
            OR blocks < 0
            OR turnovers < 0
            OR personal_fouls < 0
        """
    ).fetchone()

    assert result[0] == 0


def test_percentage_fields_are_valid(
    db_connection,
):
    """
    Basketball percentage fields must remain
    between 0 and 1 when populated.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE
            (
                field_goal_pct IS NOT NULL
                AND (
                    field_goal_pct < 0
                    OR field_goal_pct > 1
                )
            )
            OR (
                three_point_pct IS NOT NULL
                AND (
                    three_point_pct < 0
                    OR three_point_pct > 1
                )
            )
            OR (
                free_throw_pct IS NOT NULL
                AND (
                    free_throw_pct < 0
                    OR free_throw_pct > 1
                )
            )
        """
    ).fetchone()

    assert result[0] == 0


def test_recent_minutes_values_are_nonnegative(
    db_connection,
):
    """
    Rolling recent-minutes values must be valid
    nonnegative numeric values.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        WHERE
            recent_minutes_avg IS NOT NULL
            AND recent_minutes_avg < 0
        """
    ).fetchone()

    assert result[0] == 0


def test_database_contains_valid_data(
    db_connection,
):
    """
    The integrity suite should run against a populated
    test environment rather than an empty database.
    """

    result = db_connection.execute(
        """
        SELECT COUNT(*)
        FROM player_game_stats
        """
    ).fetchone()

    assert result[0] > 0