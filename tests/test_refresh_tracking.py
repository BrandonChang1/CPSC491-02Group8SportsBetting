"""Real PostgreSQL refresh/attempt transactions in disposable, temporary tables."""

import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import psycopg
import pytest
import requests

from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion import database_ingestion as ingestion
from data.ingestion import incremental_refresh as refresh

PLAYER = 201939
SEASON = "2024-25"


@pytest.fixture
def scope(monkeypatch, espn_responses):
    logs = fetch_player_game_log(PLAYER, SEASON).assign(game_date=pd.Timestamp("2025-01-01"))
    with psycopg.connect(ingestion.get_database_url(), autocommit=True) as connection:
        connection.execute(Path("database/schema.sql").read_text().replace("CREATE TABLE", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO teams (id, full_name, abbreviation)
            VALUES (1, 'Home', 'GSW'), (2, 'Away', 'LAC');
            INSERT INTO players (id, full_name, is_active, team_id)
            VALUES (201939, 'Test Player', TRUE, 1)
        """)
        monkeypatch.setattr(refresh.psycopg, "connect", lambda *args, **kwargs: nullcontext(connection))
        monkeypatch.setattr(refresh, "fetch_player_game_log", Mock(return_value=logs))
        yield connection, logs


def history(connection):
    return connection.execute("""
        SELECT s.*, g.game_date, g.home_team_id, g.away_team_id
        FROM player_game_stats s JOIN games g ON g.id = s.game_id
        ORDER BY g.game_date, s.game_id
    """).fetchall()


def test_incremental_refresh_records_success_preserves_history_and_retries(scope):
    connection, logs = scope
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    before = history(connection)
    first = refresh.get_refresh_status(PLAYER, SEASON)
    assert first["status"] == "succeeded"
    assert first["source"] == "ESPN"
    assert first["inserted_rows"] == first["source_rows"] == 1
    assert first["started_at"] <= first["finished_at"] == first["last_successful_refresh"]
    assert not first["is_stale"]
    new = logs.assign(game_id="refresh-2", game_date=pd.Timestamp("2025-01-03"), minutes=30)
    refresh.fetch_player_game_log.return_value = pd.concat([logs, new], ignore_index=True)
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    after = history(connection)
    assert len(after) == 2 and after[:1] == before
    assert connection.execute("SELECT recent_minutes_avg FROM player_game_stats WHERE game_id='refresh-2'").fetchone() == (38.0,)
    second = refresh.get_refresh_status(PLAYER, SEASON)
    assert (second["source_rows"], second["inserted_rows"], second["skipped_rows"]) == (2, 1, 1)
    assert second["last_successful_refresh"] > first["last_successful_refresh"]
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert history(connection) == after
    retry = refresh.get_refresh_status(PLAYER, SEASON)
    assert (retry["source_rows"], retry["inserted_rows"], retry["skipped_rows"]) == (2, 0, 2)
    assert connection.execute("SELECT COUNT(*) FROM ingestion_refresh_runs").fetchone() == (3,)


def test_failed_api_attempt_is_durable_and_does_not_advance_last_success(scope, caplog):
    connection, _ = scope
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    prior = refresh.get_refresh_status(PLAYER, SEASON)
    before = history(connection)

    def timeout(*args):
        assert connection.execute("SELECT status, finished_at FROM ingestion_refresh_runs ORDER BY id DESC LIMIT 1").fetchone() == ("running", None)
        raise requests.Timeout("postgresql://private-user:private-password@private-host/db")

    refresh.fetch_player_game_log.side_effect = timeout
    assert refresh.refresh_player(PLAYER, SEASON) == 1
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["status"] == "failed" and status["error_type"] == "Timeout"
    assert status["last_successful_refresh"] == prior["last_successful_refresh"]
    assert status["finished_at"] >= status["started_at"]
    assert history(connection) == before
    assert "refresh_failed" in caplog.text
    for secret in ["private-user", "private-password", "private-host"]:
        assert secret not in caplog.text
        assert secret not in str(connection.execute("SELECT error_type FROM ingestion_refresh_runs").fetchall())


def test_failed_batch_rolls_back_all_games_and_stats_then_recovers(scope):
    connection, logs = scope
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    prior = refresh.get_refresh_status(PLAYER, SEASON)
    before = history(connection)
    good = logs.assign(game_id="new-good", game_date=pd.Timestamp("2025-01-02"))
    bad = logs.assign(game_id="new-bad", game_date=pd.Timestamp("2025-01-03"), field_goals_made="invalid")
    refresh.fetch_player_game_log.return_value = pd.concat([logs, good, bad], ignore_index=True)
    assert refresh.refresh_player(PLAYER, SEASON) == 1
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["status"] == "failed" and status["inserted_rows"] == 0
    assert status["last_successful_refresh"] == prior["last_successful_refresh"]
    assert history(connection) == before
    assert connection.execute("SELECT COUNT(*) FROM games").fetchone() == (1,)
    fixed = bad.assign(field_goals_made=10)
    refresh.fetch_player_game_log.return_value = pd.concat([logs, good, fixed], ignore_index=True)
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert len(history(connection)) == 3
    assert history(connection)[:1] == before


def test_existing_values_and_legacy_game_identity_are_preserved(scope):
    connection, logs = scope
    legacy = logs.assign(game_id="legacy-game")
    assert ingestion.ingest_games(legacy)["failed"] == 0
    assert ingestion.ingest_player_game_stats(legacy)["failed"] == 0
    before = history(connection)
    refresh.fetch_player_game_log.return_value = logs.assign(points=999)
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert history(connection) == before
    assert connection.execute("SELECT id FROM games").fetchall() == [("legacy-game",)]
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert (status["inserted_rows"], status["skipped_rows"]) == (0, 1)


def test_source_gap_is_filled_and_rolling_minutes_use_full_history(scope):
    connection, logs = scope
    refresh.fetch_player_game_log.return_value = logs.assign(game_date=pd.Timestamp("2025-01-05"))
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    refresh.fetch_player_game_log.return_value = logs.assign(game_id="missed-game", minutes=20, game_date=pd.Timestamp("2025-01-03"))
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert connection.execute("""
        SELECT s.game_id, s.minutes, s.points, s.recent_minutes_avg
        FROM player_game_stats s JOIN games g ON s.game_id=g.id ORDER BY g.game_date
    """).fetchall() == [("missed-game", 20, 36, None), (logs.iloc[0]["game_id"], 38, 36, 20.0)]


@pytest.mark.parametrize("failure", ["empty", "wrong-player", "identity-conflict", "duplicate", "duplicate-provider-id", "negative", "nan", "future", "postprocessing"])
def test_invalid_or_incomplete_refresh_cannot_become_success(scope, monkeypatch, failure):
    connection, logs = scope
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    prior = refresh.get_refresh_status(PLAYER, SEASON)
    before = history(connection)
    if failure == "empty":
        refresh.fetch_player_game_log.return_value = pd.DataFrame()
    elif failure == "wrong-player":
        refresh.fetch_player_game_log.return_value = logs.assign(player_id=999)
    elif failure == "identity-conflict":
        refresh.fetch_player_game_log.return_value = logs.assign(game_date=pd.Timestamp("2025-01-03"))
    elif failure == "duplicate":
        refresh.fetch_player_game_log.return_value = pd.concat([logs, logs], ignore_index=True)
    elif failure == "duplicate-provider-id":
        new = logs.assign(game_id="new-a", game_date=pd.Timestamp("2025-01-03"))
        refresh.fetch_player_game_log.return_value = pd.concat([new, new.assign(game_id="new-b")], ignore_index=True)
    elif failure in ("negative", "nan", "future"):
        values = {"negative": -1, "nan": float("nan"), "future": 36}
        refresh.fetch_player_game_log.return_value = logs.assign(
            game_id="invalid-new", points=values[failure],
            game_date=pd.Timestamp("2099-01-03" if failure == "future" else "2025-01-03"),
        )
    else:
        refresh.fetch_player_game_log.return_value = logs.assign(game_id="new-game", game_date=pd.Timestamp("2025-01-03"))
        monkeypatch.setattr(refresh, "recalculate_recent_minutes_avg", Mock(side_effect=psycopg.OperationalError("private error")))
    assert refresh.refresh_player(PLAYER, SEASON) == 1
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["status"] == "failed"
    assert status["last_successful_refresh"] == prior["last_successful_refresh"]
    assert history(connection) == before


def test_interrupted_write_rolls_back_and_leaves_visible_running_attempt(scope, monkeypatch):
    connection, logs = scope
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    before = history(connection)
    prior = refresh.get_refresh_status(PLAYER, SEASON)
    refresh.fetch_player_game_log.return_value = logs.assign(game_id="interrupted", game_date=pd.Timestamp("2025-01-03"))
    original = refresh.ingest_player_game_stats

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(refresh, "ingest_player_game_stats", interrupt)
    with pytest.raises(KeyboardInterrupt):
        refresh.refresh_player(PLAYER, SEASON)
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["status"] == "running" and status["finished_at"] is None
    assert status["last_successful_refresh"] == prior["last_successful_refresh"]
    assert history(connection) == before


def test_status_separates_scope_latest_failure_and_stale_success(scope):
    connection, _ = scope
    assert refresh.get_refresh_status(PLAYER, SEASON) is None
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert refresh.get_refresh_status(PLAYER, "2025-26") is None
    assert refresh.get_refresh_status(999, SEASON) is None
    connection.execute("""
        UPDATE ingestion_refresh_runs SET started_at=clock_timestamp()-INTERVAL '50 hours',
        finished_at=clock_timestamp()-INTERVAL '49 hours'
    """)
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["status"] == "succeeded" and status["is_stale"]


@pytest.mark.parametrize(("player_id", "season"), [(0, SEASON), (-1, SEASON), (PLAYER, "2024-26")])
def test_invalid_scope_is_rejected_before_database_access(monkeypatch, player_id, season):
    connect = Mock()
    monkeypatch.setattr(refresh.psycopg, "connect", connect)
    with pytest.raises(ValueError):
        refresh.refresh_player(player_id, season)
    connect.assert_not_called()


@pytest.mark.parametrize(("status", "stale", "expected"), [("succeeded", False, 0), ("failed", False, 1), ("running", False, 1), ("succeeded", True, 1), (None, True, 1)])
def test_status_command_reports_monitoring_exit_status(monkeypatch, capsys, status, stale, expected):
    value = {"status": status, "is_stale": stale} if status else None
    monkeypatch.setattr(refresh, "get_refresh_status", lambda *args: value)
    monkeypatch.setattr("sys.argv", ["refresh", "--player-id", str(PLAYER), "--season", SEASON, "--status"])
    assert refresh.main() == expected
    assert json.loads(capsys.readouterr().out) == value
