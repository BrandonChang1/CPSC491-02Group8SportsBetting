"""Offline failure simulations: safe diagnostics, partial results and exit status."""

import logging
from unittest.mock import MagicMock, Mock

import pandas as pd
import psycopg
import pytest
import requests

from data.collection import espn
from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion import database_ingestion as ingestion
from data.ingestion import historical_backfill as backfill
from data.ingestion.monitoring import run

SENSITIVE = "postgresql://audit_user:DO_NOT_LOG_PASSWORD@db.invalid/nba?token=DO_NOT_LOG_TOKEN"
SUCCESS = {"processed": 1, "successful": 1, "failed": 0}
PARTIAL = {"processed": 2, "successful": 1, "failed": 1}


def assert_safe(caplog, capsys):
    captured = capsys.readouterr()
    output = caplog.text + captured.out + captured.err
    for secret in ("DO_NOT_LOG_PASSWORD", "DO_NOT_LOG_TOKEN", "audit_user", "db.invalid"):
        assert secret not in output
    assert not any(record.exc_info for record in caplog.records)


@pytest.fixture
def game_logs(espn_responses):
    return fetch_player_game_log(201939, "2024-25")


@pytest.mark.parametrize("stage", ["teams", "players", "games", "player_game_stats"])
@pytest.mark.parametrize("error_class", [psycopg.IntegrityError, psycopg.OperationalError, KeyError])
def test_row_failure_is_safe_counted_and_followed_by_success(
    monkeypatch, caplog, capsys, game_logs, stage, error_class,
):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.side_effect = [error_class(SENSITIVE), Mock()]
    monkeypatch.setattr(ingestion.psycopg, "connect", Mock(return_value=connection))
    monkeypatch.setattr(ingestion, "get_database_url", lambda: SENSITIVE)
    monkeypatch.setattr(ingestion, "get_team_id_map", lambda connection: {"GSW": 1, "LAC": 2})
    monkeypatch.setattr(ingestion, "canonical_game_id", lambda connection, row, team_ids: row["game_id"])
    monkeypatch.setattr(ingestion, "refresh_player_team_ids", Mock())
    if stage == "teams":
        monkeypatch.setattr(ingestion.teams, "get_teams", Mock(return_value=[
            {"id": n, "full_name": "Test", "abbreviation": "T", "city": "Test"} for n in (1, 2)
        ]))
        result = ingestion.ingest_teams()
    elif stage == "players":
        monkeypatch.setattr(ingestion.players, "get_players", Mock(return_value=[
            {"id": n, "full_name": "Test", "first_name": "Test", "last_name": "Player",
             "is_active": True, "team_id": 1} for n in (1, 2)
        ]))
        result = ingestion.ingest_players()
    else:
        logs = pd.concat([game_logs, game_logs.assign(game_id="second-game")], ignore_index=True)
        result = getattr(ingestion, f"ingest_{stage}")(logs)
    assert result == PARTIAL
    assert connection.execute.call_count == 2
    assert f"stage={stage} row=1 error_type={error_class.__name__}" in caplog.text
    assert_safe(caplog, capsys)


@pytest.mark.parametrize("error_class", [requests.Timeout, requests.HTTPError])
def test_real_api_request_failure_is_safely_reported(monkeypatch, caplog, capsys, error_class):
    monkeypatch.setattr(espn.requests, "get", Mock(side_effect=error_class(SENSITIVE)))
    assert run(lambda: espn.request_json(espn.SITE, "teams")) == 1
    assert f"ingestion_failed command={__name__} error_type={error_class.__name__}" in caplog.text
    assert_safe(caplog, capsys)


def test_database_connection_failure_is_safely_reported(monkeypatch, caplog, capsys):
    monkeypatch.setattr(ingestion.teams, "get_teams", list)
    monkeypatch.setattr(ingestion, "get_database_url", lambda: SENSITIVE)
    monkeypatch.setattr(ingestion.psycopg, "connect", Mock(side_effect=psycopg.OperationalError(SENSITIVE)))
    assert run(ingestion.main) == 1
    assert "error_type=OperationalError" in caplog.text
    assert_safe(caplog, capsys)


@pytest.fixture
def command_stages(monkeypatch, game_logs):
    for module in (ingestion, backfill):
        for name in ("ingest_teams", "ingest_players", "ingest_games", "ingest_player_game_stats"):
            monkeypatch.setattr(module, name, Mock(return_value=SUCCESS.copy()))
        monkeypatch.setattr(module, "fetch_player_game_log", Mock(return_value=game_logs))
    player = {"id": 201939, "full_name": "Test Player"}
    monkeypatch.setattr(ingestion.players, "find_players_by_full_name", lambda name: [player])
    monkeypatch.setattr(backfill.players, "get_active_players", lambda: [player])
    monkeypatch.setattr(backfill, "TARGET_STAT_ROWS", 1)
    monkeypatch.setattr(backfill, "get_player_game_stat_count", Mock(side_effect=[0, 1, 1]))
    monkeypatch.setattr(backfill, "recalculate_recent_minutes_avg", Mock())
    monkeypatch.setattr(backfill.time, "sleep", Mock())


@pytest.mark.parametrize("module", [ingestion, backfill], ids=["ingestion", "backfill"])
@pytest.mark.parametrize("stage", ["ingest_teams", "ingest_players", "ingest_games", "ingest_player_game_stats"])
def test_partial_stage_causes_nonzero_status(module, stage, command_stages, caplog):
    getattr(module, stage).return_value = PARTIAL.copy()
    assert run(module.main) == 1
    assert "incomplete" in caplog.text


@pytest.mark.parametrize("module", [ingestion, backfill], ids=["ingestion", "backfill"])
def test_successful_command_returns_zero(module, command_stages, caplog):
    assert run(module.main) == 0
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


@pytest.mark.parametrize("error_class", [requests.Timeout, ValueError, psycopg.OperationalError])
def test_backfill_catches_player_failure_without_leaking(
    error_class, command_stages, caplog, capsys,
):
    backfill.fetch_player_game_log.side_effect = error_class(SENSITIVE)
    assert run(backfill.main) == 1
    assert "player_season_failed player_id=201939 season=2024-25" in caplog.text
    assert f"error_type={error_class.__name__}" in caplog.text
    assert_safe(caplog, capsys)


def test_backfill_continues_with_next_player(monkeypatch, command_stages, game_logs, caplog):
    monkeypatch.setattr(backfill.players, "get_active_players", lambda: [
        {"id": 1, "full_name": "First"}, {"id": 2, "full_name": "Second"},
    ])
    backfill.fetch_player_game_log.side_effect = [requests.Timeout(SENSITIVE), game_logs]
    backfill.get_player_game_stat_count.side_effect = [0, 0, 1, 1]
    assert run(backfill.main) == 1
    assert backfill.fetch_player_game_log.call_count == 2
    backfill.ingest_games.assert_called_once_with(game_logs)
    assert "player_season_failed player_id=1" in caplog.text


@pytest.mark.parametrize("module", [ingestion, backfill], ids=["ingestion", "backfill"])
def test_empty_history_is_visible(module, command_stages, caplog):
    module.fetch_player_game_log.return_value = pd.DataFrame()
    if module is backfill:
        backfill.get_player_game_stat_count.side_effect = [0, 0, 0]
    assert run(module.main) == 1
    assert "empty_response" in caplog.text or "no_game_logs" in caplog.text
    module.ingest_games.assert_not_called()


def test_postprocessing_database_failure_is_safe(command_stages, caplog, capsys):
    backfill.recalculate_recent_minutes_avg.side_effect = psycopg.OperationalError(SENSITIVE)
    assert run(backfill.main) == 1
    assert "ingestion_failed" in caplog.text
    assert_safe(caplog, capsys)
