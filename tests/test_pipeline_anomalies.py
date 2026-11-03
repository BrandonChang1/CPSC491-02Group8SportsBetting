"""Read-only checks of stored ingestion data, plus isolated detector tests."""

import psycopg
import pytest

from data.ingestion.database_ingestion import get_database_url

# Each query returns the identities of offending records for pytest's failure report.
ANOMALY_QUERIES = {
    "duplicate_player_games": """
        SELECT player_id, game_id, COUNT(*)
        FROM player_game_stats
        GROUP BY player_id, game_id HAVING COUNT(*) > 1
    """,
    "duplicate_game_identities": """
        SELECT game_date, home_team_id, away_team_id, COUNT(*)
        FROM games
        GROUP BY game_date, home_team_id, away_team_id HAVING COUNT(*) > 1
    """,
    "missing_required_stats": """
        SELECT player_id, game_id FROM player_game_stats
        WHERE player_id IS NULL OR game_id IS NULL OR minutes IS NULL
           OR points IS NULL OR rebounds IS NULL OR assists IS NULL
           OR opponent_team_id IS NULL OR is_home IS NULL
    """,
    "invalid_numeric_stats": """
        SELECT DISTINCT player_id, game_id FROM player_game_stats
        CROSS JOIN LATERAL unnest(ARRAY[
            minutes, points, rebounds, assists, field_goals_made,
            field_goals_attempted, three_pointers_made, three_pointers_attempted,
            free_throws_made, free_throws_attempted, offensive_rebounds,
            defensive_rebounds, steals, blocks, turnovers, personal_fouls,
            recent_minutes_avg
        ]) AS stats(value)
        WHERE value < 0 OR value IN ('NaN'::double precision, 'Infinity'::double precision)
    """,
    "invalid_percentages": """
        SELECT DISTINCT player_id, game_id FROM player_game_stats
        CROSS JOIN LATERAL unnest(ARRAY[
            field_goal_pct, three_point_pct, free_throw_pct
        ]) AS percentages(value)
        WHERE value < 0 OR value > 1
    """,
    "inconsistent_stat_totals": """
        SELECT player_id, game_id FROM player_game_stats
        WHERE field_goals_made > field_goals_attempted
           OR three_pointers_made > three_pointers_attempted
           OR free_throws_made > free_throws_attempted
           OR three_pointers_made > field_goals_made
           OR three_pointers_attempted > field_goals_attempted
           OR points <> 2::bigint * field_goals_made + three_pointers_made + free_throws_made
           OR rebounds <> offensive_rebounds::bigint + defensive_rebounds
    """,
    "invalid_game_context": """
        SELECT s.player_id, s.game_id FROM player_game_stats s
        LEFT JOIN games g ON g.id = s.game_id
        WHERE g.id IS NULL OR g.game_date IS NULL
           OR g.home_team_id IS NULL OR g.away_team_id IS NULL
           OR g.home_team_id = g.away_team_id
           OR s.opponent_team_id IS DISTINCT FROM
               CASE WHEN s.is_home THEN g.away_team_id ELSE g.home_team_id END
    """,
}


@pytest.fixture
def anomaly_connection():
    # Roll back even on failure; synthetic detector tests must never persist data.
    with (
        psycopg.connect(get_database_url()) as connection,
        connection.transaction(force_rollback=True),
    ):
        yield connection


@pytest.mark.parametrize("check", ANOMALY_QUERIES)
def test_stored_pipeline_has_no_anomalies(anomaly_connection, check):
    anomaly_connection.execute("SET TRANSACTION READ ONLY")
    assert anomaly_connection.execute(
        "SELECT EXISTS (SELECT 1 FROM player_game_stats)"
    ).fetchone()[0], "No player-game records: an empty database cannot pass the anomaly audit"
    rows = anomaly_connection.execute(ANOMALY_QUERIES[check]).fetchall()
    assert not rows, f"{check}: anomalous records (player/game or game identity): {rows}"


@pytest.fixture
def detector_records(anomaly_connection):
    # Temporary snapshots omit constraints so corrupt records can exercise detection.
    for table in ("games", "player_game_stats"):
        anomaly_connection.execute(
            f"CREATE TEMP TABLE {table} AS SELECT * FROM public.{table} WITH NO DATA"
        )
    anomaly_connection.execute("""
        INSERT INTO games (id, game_date, home_team_id, away_team_id)
        VALUES ('anomaly-test', '2025-01-01', 1, 2)
    """)
    anomaly_connection.execute("""
        INSERT INTO player_game_stats (
            player_id, game_id, minutes, points, rebounds, assists,
            field_goals_made, field_goals_attempted, three_pointers_made,
            three_pointers_attempted, free_throws_made, free_throws_attempted,
            offensive_rebounds, defensive_rebounds, field_goal_pct,
            three_point_pct, free_throw_pct, opponent_team_id, is_home,
            plus_minus, recent_minutes_avg
        ) VALUES (
            10, 'anomaly-test', 53, 20, 5, 6, 7, 14, 2, 5, 4, 4,
            1, 4, 0.5, 0.4, 1.0, 2, TRUE, -10, NULL
        )
    """)
    return anomaly_connection


@pytest.mark.parametrize("check", ANOMALY_QUERIES)
def test_detectors_accept_valid_records(detector_records, check):
    # Overtime minutes, negative plus/minus and a first-game NULL average are valid.
    assert detector_records.execute(ANOMALY_QUERIES[check]).fetchall() == []


@pytest.mark.parametrize(("check", "mutation"), [
    ("duplicate_player_games", "INSERT INTO player_game_stats SELECT * FROM player_game_stats"),
    ("duplicate_game_identities", "INSERT INTO games SELECT 'other-id', game_date, home_team_id, away_team_id FROM games"),
    ("missing_required_stats", "UPDATE player_game_stats SET points = NULL"),
    ("invalid_numeric_stats", "UPDATE player_game_stats SET assists = -1"),
    ("invalid_numeric_stats", "UPDATE player_game_stats SET recent_minutes_avg = 'NaN'"),
    ("invalid_numeric_stats", "UPDATE player_game_stats SET recent_minutes_avg = 'Infinity'"),
    ("invalid_numeric_stats", "UPDATE player_game_stats SET recent_minutes_avg = '-Infinity'"),
    ("invalid_percentages", "UPDATE player_game_stats SET field_goal_pct = 1.1"),
    ("invalid_percentages", "UPDATE player_game_stats SET three_point_pct = -0.1"),
    ("invalid_percentages", "UPDATE player_game_stats SET free_throw_pct = 'NaN'"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET field_goals_attempted = 6"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET three_pointers_attempted = 1"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET free_throws_attempted = 3"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET three_pointers_made = 8"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET three_pointers_attempted = 15"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET points = 21"),
    ("inconsistent_stat_totals", "UPDATE player_game_stats SET rebounds = 6"),
    ("invalid_game_context", "UPDATE player_game_stats SET opponent_team_id = 1"),
    ("invalid_game_context", "UPDATE player_game_stats SET is_home = FALSE"),
    ("invalid_game_context", "DELETE FROM games"),
    ("invalid_game_context", "UPDATE games SET away_team_id = home_team_id"),
])
def test_detectors_flag_corrupt_records(detector_records, check, mutation):
    detector_records.execute(mutation)
    rows = detector_records.execute(ANOMALY_QUERIES[check]).fetchall()
    assert len(rows) == 1, f"{check} did not identify the injected anomaly: {rows}"
    if check != "duplicate_game_identities":
        assert rows[0][:2] == (10, "anomaly-test")
