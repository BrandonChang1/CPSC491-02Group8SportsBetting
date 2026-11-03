"""Actual PostgreSQL upserts in connection-local tables; no stored data changes."""

from contextlib import nullcontext
from datetime import date
from pathlib import Path

import psycopg
import pytest

from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion import database_ingestion as ingestion
from scripts.check_data_freshness import check_freshness


@pytest.fixture
def refresh_data(monkeypatch, espn_responses):
    logs = fetch_player_game_log(201939, "2024-25").assign(game_date="2025-01-01")
    # Temp tables and indexes disappear on disconnect, including after a failed test.
    with psycopg.connect(ingestion.get_database_url(), autocommit=True) as connection:
        schema = Path("database/schema.sql").read_text()
        connection.execute(schema.replace("CREATE TABLE", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO teams (id, full_name, abbreviation)
            VALUES (1, 'Home', 'GSW'), (2, 'Away', 'LAC');
            INSERT INTO players (id, full_name, is_active, team_id)
            VALUES (201939, 'Test Player', TRUE, 1);
        """)
        monkeypatch.setattr(ingestion.psycopg, "connect", lambda *args, **kwargs: nullcontext(connection))
        assert ingestion.ingest_games(logs)["failed"] == 0
        assert ingestion.ingest_player_game_stats(logs)["failed"] == 0
        yield connection, logs


def stored_rows(connection):
    return connection.execute("""
        SELECT s.*, g.game_date, g.home_team_id, g.away_team_id
        FROM player_game_stats s JOIN games g ON g.id = s.game_id
        ORDER BY s.player_id, g.game_date, s.game_id
    """).fetchall()


def test_incremental_insert_and_retry_preserve_history(refresh_data):
    connection, logs = refresh_data
    before = stored_rows(connection)
    new = logs.assign(game_id="refresh-new", game_date="2025-01-03", minutes=32)
    assert ingestion.ingest_games(new)["failed"] == 0
    assert ingestion.ingest_player_game_stats(new)["failed"] == 0
    after = stored_rows(connection)
    assert len(after) == 2
    assert after[:1] == before
    assert check_freshness(connection, 201939, date(2025, 1, 3), date(2025, 1, 6)) == 0
    assert ingestion.ingest_games(new)["failed"] == 0
    assert ingestion.ingest_player_game_stats(new)["failed"] == 0
    assert stored_rows(connection) == after


def test_failed_refresh_retains_history_and_recovers(refresh_data, caplog):
    connection, logs = refresh_data
    before = stored_rows(connection)
    new = logs.assign(game_id="refresh-new", game_date="2025-01-03")
    assert ingestion.ingest_games(new)["failed"] == 0
    result = ingestion.ingest_player_game_stats(new.assign(player_id=999999999))
    assert result == {"processed": 1, "successful": 0, "failed": 1}
    assert stored_rows(connection) == before
    # A game shell without player stats must not satisfy the freshness check.
    assert check_freshness(connection, 201939, date(2025, 1, 3), date(2025, 1, 6)) == 1
    assert "row_failed stage=player_game_stats" in caplog.text
    assert "missing_expected_game" in caplog.text
    assert ingestion.ingest_player_game_stats(new)["failed"] == 0
    assert stored_rows(connection)[:1] == before
    assert check_freshness(connection, 201939, date(2025, 1, 3), date(2025, 1, 6)) == 0


def test_changed_game_identity_cannot_overwrite_history(refresh_data, caplog):
    connection, logs = refresh_data
    before = stored_rows(connection)
    invalid = logs.assign(game_date="2025-01-03", points=999)
    assert ingestion.ingest_games(invalid)["failed"] == 1
    assert ingestion.ingest_player_game_stats(invalid)["failed"] == 1
    assert stored_rows(connection) == before
    assert "error_type=ValueError" in caplog.text


def test_failed_update_preserves_existing_values(refresh_data, caplog):
    connection, logs = refresh_data
    before = stored_rows(connection)
    invalid = logs.assign(points="not-a-number")
    assert ingestion.ingest_player_game_stats(invalid)["failed"] == 1
    assert stored_rows(connection) == before
    assert "row_failed stage=player_game_stats" in caplog.text
    assert "error_type=InvalidTextRepresentation" in caplog.text


def test_truncated_refresh_does_not_delete_history(refresh_data):
    connection, logs = refresh_data
    new = logs.assign(game_id="refresh-new", game_date="2025-01-03")
    assert ingestion.ingest_games(new)["failed"] == 0
    assert ingestion.ingest_player_game_stats(new)["failed"] == 0
    before = stored_rows(connection)
    assert ingestion.ingest_games(logs)["failed"] == 0
    assert ingestion.ingest_player_game_stats(logs)["failed"] == 0
    assert stored_rows(connection) == before


def test_freshness_monitor_cannot_hide_missing_date_with_newer_data(refresh_data):
    connection, logs = refresh_data
    new = logs.assign(game_id="refresh-new", game_date="2025-01-05")
    assert ingestion.ingest_games(new)["failed"] == 0
    assert ingestion.ingest_player_game_stats(new)["failed"] == 0
    before = stored_rows(connection)
    assert check_freshness(connection, 201939, date(2025, 1, 3), date(2025, 1, 6)) == 1
    assert stored_rows(connection) == before
