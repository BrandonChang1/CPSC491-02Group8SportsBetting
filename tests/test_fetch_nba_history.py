"""Unit tests for NBA history retrieval, without live API requests."""
import json
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ml import fetch_nba_history


def test_seasons_to_try_after_season_start():
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    assert fetch_nba_history.seasons_to_try(now) == ["2026-27", "2025-26"]


def test_seasons_to_try_before_season_start():
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    assert fetch_nba_history.seasons_to_try(now) == ["2025-26", "2024-25"]


def test_fetch_games_sorts_deduplicates_and_cleans(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26", "2024-25"])
    frames = {
        "2025-26": pd.DataFrame([
            {"GAME_DATE": "2025-10-24", "Game_ID": "002", "PTS": "30"},
            {"GAME_DATE": "2025-10-22", "Game_ID": "001", "PTS": "20"},
            {"GAME_DATE": "2025-10-23", "Game_ID": "bad", "PTS": "n/a"},
            {"GAME_DATE": "2025-10-25", "Game_ID": "nan", "PTS": float("nan")},
            {"GAME_DATE": "", "Game_ID": "empty", "PTS": 14},
        ]),
        "2024-25": pd.DataFrame([
            {"GAME_DATE": "2025-10-22", "Game_ID": "001", "PTS": 21},
            {"GAME_DATE": "2025-04-01", "Game_ID": "old", "PTS": 10},
        ]),
    }
    api = MagicMock()
    api.side_effect = lambda **kwargs: MagicMock(get_data_frames=lambda: [frames[kwargs["season"]]])
    monkeypatch.setattr(fetch_nba_history.playergamelog, "PlayerGameLog", api)

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
    api.assert_any_call(player_id=123, season="2025-26", season_type_all_star="Regular Season", timeout=15)


def test_fetch_games_reports_empty_history(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26"])
    monkeypatch.setattr(
        fetch_nba_history.playergamelog,
        "PlayerGameLog",
        lambda **kwargs: MagicMock(get_data_frames=lambda: [pd.DataFrame()]),
    )
    assert fetch_nba_history.fetch_games(123) == {
        "success": False,
        "games": [],
        "message": "No NBA game history available from nba_api.",
        "errors": [],
    }


def test_fetch_games_keeps_partial_results_when_api_fails(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26", "2024-25"])

    def fake_api(**kwargs):
        if kwargs["season"] == "2025-26":
            raise TimeoutError("timeout")
        return MagicMock(get_data_frames=lambda: [pd.DataFrame([
            {"GAME_DATE": "2025-04-01", "Game_ID": "001", "PTS": 17},
        ])])

    monkeypatch.setattr(fetch_nba_history.playergamelog, "PlayerGameLog", fake_api)
    result = fetch_nba_history.fetch_games(123)
    assert result["success"] is True
    assert result["games"] == [{"game_date": "2025-04-01", "points": 17.0}]
    assert result["errors"] == ["2025-26: timeout"]


def test_fetch_games_handles_total_api_failure(monkeypatch):
    monkeypatch.setattr(fetch_nba_history, "seasons_to_try", lambda: ["2025-26"])

    def fail(**kwargs):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(fetch_nba_history.playergamelog, "PlayerGameLog", fail)
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
