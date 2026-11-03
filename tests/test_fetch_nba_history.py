"""Unit tests for NBA history retrieval, without live API requests."""
import json
import sys
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from ml import fetch_nba_history


def test_seasons_to_try_after_season_start():
    now = datetime(2026, 10, 12, tzinfo=UTC)
    assert fetch_nba_history.seasons_to_try(now) == ["2026-27", "2025-26"]


def test_seasons_to_try_before_season_start():
    now = datetime(2026, 9, 30, tzinfo=UTC)
    assert fetch_nba_history.seasons_to_try(now) == ["2025-26", "2024-25"]


def test_fetch_games_sorts_deduplicates_and_cleans(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26", "2024-25"])
    def event(date, points):
        return {"gameDate": date, "stats": {"points": points}}

    frames = {
        "2025-26": {
            "002": event("2025-10-24T20:00Z", "30"),
            "001": event("2025-10-22T20:00Z", "20"),
            "bad": event("2025-10-23T20:00Z", "n/a"),
            "nan": event("2025-10-25T20:00Z", float("nan")),
            "infinite": event("2025-10-25T20:00Z", float("inf")),
            "empty": event("", 14),
            "negative": event("2025-10-26T20:00Z", -1),
        },
        "2024-25": {
            "001": event("2025-10-22T20:00Z", 21),
            "old": event("2025-04-01T20:00Z", 10),
        },
    }
    api = Mock(side_effect=lambda player_id, season: frames[season])
    monkeypatch.setattr(fetch_nba_history, "player_events", api)

    result = fetch_nba_history.fetch_games(123)

    assert result == {
        "success": True,
        "games": [
            {"game_date": "2025-04-01", "points": 10.0},
            {"game_date": "2025-10-22", "points": 21.0},
            {"game_date": "2025-10-24", "points": 30.0},
        ],
        "message": "",
        "errors": [],
    }
    assert api.call_count == 2
    api.assert_any_call(123, "2025-26")


def test_fetch_games_reports_empty_history(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26"])
    monkeypatch.setattr(fetch_nba_history, "player_events", lambda *args: {})
    assert fetch_nba_history.fetch_games(123) == {
        "success": False,
        "games": [],
        "message": "No NBA game history available from ESPN.",
        "errors": [],
    }


def test_fetch_games_keeps_partial_results_when_api_fails(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26", "2024-25"])

    def fake_api(player_id, season):
        if season == "2025-26":
            raise TimeoutError("timeout")
        return {"001": {"gameDate": "2025-04-01T20:00Z", "stats": {"points": 17}}}

    monkeypatch.setattr(fetch_nba_history, "player_events", fake_api)
    result = fetch_nba_history.fetch_games(123)
    assert result["success"] is True
    assert result["games"] == [{"game_date": "2025-04-01", "points": 17.0}]
    assert result["errors"] == ["2025-26: timeout"]


def test_fetch_games_handles_total_api_failure(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26"])

    def fail(*args):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(fetch_nba_history, "player_events", fail)
    result = fetch_nba_history.fetch_games(123)
    assert result["success"] is False
    assert result["games"] == []
    assert result["errors"] == ["2025-26: API unavailable"]


@pytest.mark.parametrize("args", [["fetch_nba_history.py"], ["fetch_nba_history.py", "abc"], ["fetch_nba_history.py", "123", "456"]])
def test_main_rejects_invalid_id(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", args)
    fetch_nba_history.main()
    assert json.loads(capsys.readouterr().out) == {
        "success": False, "games": [], "message": "Valid player ID required."
    }


def test_main_accepts_numeric_id(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["fetch_nba_history.py", "123"])
    recorded = []
    monkeypatch.setattr(fetch_nba_history, "fetch_games", lambda player_id: recorded.append(player_id) or {"success": True, "games": []})
    fetch_nba_history.main()
    assert recorded == [123]
    assert json.loads(capsys.readouterr().out)["success"] is True
