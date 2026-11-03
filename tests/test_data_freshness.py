"""Deterministic threshold and read-only command tests; no database required."""

from datetime import date
from unittest.mock import MagicMock

import psycopg
import pytest

from data.ingestion.monitoring import run
from scripts import check_data_freshness as freshness


@pytest.mark.parametrize(("latest", "count", "day", "status", "event"), [
    (date(2025, 1, 10), 1, 10, 0, "freshness_ok"),
    (date(2025, 1, 10), 1, 20, 0, "freshness_ok"),
    (date(2025, 1, 9), 0, 10, 0, "refresh_pending"),
    (date(2025, 1, 9), 0, 12, 0, "refresh_pending"),
    (date(2025, 1, 9), 0, 13, 1, "missing_expected_game"),
    (None, 0, 13, 1, "missing_expected_game"),
    (None, 0, 10, 0, "refresh_pending"),
    (date(2025, 1, 12), 0, 13, 1, "missing_expected_game"),
    (date(2025, 1, 20), 1, 13, 1, "future_record"),
    (date(2025, 1, 10), 2, 13, 1, "multiple_appearances"),
])
def test_freshness_threshold_and_missing_game(latest, count, day, status, event, caplog):
    caplog.set_level("INFO", logger="data.ingestion")
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (latest, count)
    assert freshness.check_freshness(connection, 101, date(2025, 1, 10), date(2025, 1, day)) == status
    assert event in caplog.text
    assert "player_id=101" in caplog.text
    assert connection.execute.call_args.args[1] == (date(2025, 1, 10), 101)


@pytest.mark.parametrize(("player_id", "expected"), [(0, date(2025, 1, 1)), (-1, date(2025, 1, 1)), (1, date(2025, 1, 11))])
def test_invalid_scope_is_rejected_before_query(player_id, expected):
    connection = MagicMock()
    with pytest.raises(ValueError):
        freshness.check_freshness(connection, player_id, expected, date(2025, 1, 10))
    connection.execute.assert_not_called()


def test_command_uses_read_only_transaction(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (date(2025, 1, 10), 1)
    monkeypatch.setattr(freshness.psycopg, "connect", lambda url: connection)
    monkeypatch.setattr(freshness, "get_database_url", lambda: "test-database")
    monkeypatch.setattr("sys.argv", ["check_data_freshness", "--player-id", "101",
                                  "--expected-game-date", "2025-01-10", "--as-of-date", "2025-01-13"])
    assert run(freshness.main) == 0
    assert connection.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)


def test_database_failure_has_safe_nonzero_result(monkeypatch, caplog):
    connect = MagicMock(side_effect=psycopg.OperationalError("password=private-test-password"))
    monkeypatch.setattr(freshness.psycopg, "connect", connect)
    monkeypatch.setattr(freshness, "get_database_url", lambda: "test-database")
    monkeypatch.setattr("sys.argv", ["check_data_freshness", "--player-id", "101", "--expected-game-date", "2025-01-10"])
    assert run(freshness.main) == 1
    assert "OperationalError" in caplog.text
    assert "private-test-password" not in caplog.text
