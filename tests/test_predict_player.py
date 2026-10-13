"""Unit tests for the JSON-backed next-game points baseline."""
import io
import json

import pytest

from ml import predict_player


def test_predict_calculates_season_and_recent_averages():
    games = [
        {"game_date": "2025-04-01", "points": 10},
        {"game_date": "2025-10-22", "points": 20},
        {"game_date": "2025-10-24", "points": 30},
        {"game_date": "2025-10-23", "points": 40},
    ]
    result = predict_player.predict(games)

    assert result["success"] is True
    assert result["season"] == "2025-26"
    assert result["lastGameDate"] == "2025-10-24"
    assert result["gamesAvailable"] == 4
    assert result["predictions"] == {"season": 30.0, "last5": 25.0, "last10": 25.0}
    assert "not a trained ML model" in result["model"]


@pytest.mark.parametrize("games", [[], [{"game_date": "2025-10-22"}], [{"points": 10}]])
def test_predict_rejects_empty_or_missing_columns(games):
    result = predict_player.predict(games)
    assert result == {"success": False, "message": "No historical games available for predictions."}


def test_predict_ignores_invalid_dates_and_points():
    games = [
        {"game_date": "bad date", "points": 50},
        {"game_date": "2025-10-23", "points": "not a number"},
        {"game_date": "2025-10-24", "points": "22"},
    ]
    result = predict_player.predict(games)
    assert result["success"] is True
    assert result["gamesAvailable"] == 1
    assert result["predictions"] == {"season": 22.0, "last5": 22.0, "last10": 22.0}


def test_predict_fails_when_all_rows_invalid():
    result = predict_player.predict([{"game_date": "invalid", "points": "bad"}])
    assert result == {"success": False, "message": "No valid game history available."}


def test_predict_last5_and_last10_use_most_recent_games():
    games = [
        {"game_date": f"2026-01-{day:02d}", "points": day}
        for day in range(1, 13)
    ]
    result = predict_player.predict(list(reversed(games)))
    assert result["predictions"]["season"] == 6.5
    assert result["predictions"]["last5"] == 10.0
    assert result["predictions"]["last10"] == 7.5
    assert result["lastGameDate"] == "2026-01-12"


def test_main_reads_and_writes_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"games": [{"game_date": "2026-01-01", "points": 18}]})))
    predict_player.main()
    result = json.loads(capsys.readouterr().out)
    assert result["success"] is True
    assert result["predictions"]["season"] == 18.0


def test_main_outputs_machine_readable_error_for_bad_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{invalid json"))
    with pytest.raises(SystemExit) as exc:
        predict_player.main()
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["success"] is False
