"""Unit tests for the JSON-backed trained next-game points predictor."""
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
    assert result["modelVersion"] == "random-forest-points-v1"
    assert isinstance(result["predictedPoints"], float)
    assert result["predictedPoints"] >= 0
    assert "is_home" in result["missingContext"]


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


def test_predict_fails_when_all_rows_invalid():
    result = predict_player.predict([{"game_date": "invalid", "points": "bad"}])
    assert result == {"success": False, "message": "No valid game history available."}


def test_predict_uses_latest_game_date_even_when_input_reversed():
    games = [
        {"game_date": f"2026-01-{day:02d}", "points": day}
        for day in range(1, 13)
    ]
    result = predict_player.predict(list(reversed(games)))
    assert result["lastGameDate"] == "2026-01-12"


def test_main_reads_and_writes_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"games": [{"game_date": "2026-01-01", "points": 18}]})))
    predict_player.main()
    result = json.loads(capsys.readouterr().out)
    assert result["success"] is True


def test_main_outputs_machine_readable_error_for_bad_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{invalid json"))
    with pytest.raises(SystemExit) as exc:
        predict_player.main()
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["success"] is False


def test_missing_model_returns_error_not_fake_ml_prediction(monkeypatch, tmp_path):
    monkeypatch.setattr(predict_player, "MODEL_PATH", tmp_path / "missing.joblib")
    result = predict_player.predict([{"game_date": "2026-01-02", "points": 21}])
    assert result["success"] is False
    assert "unavailable" in result["message"]
    assert "predictedPoints" not in result


def test_recent_minutes_passed_to_trained_model(monkeypatch):
    class FakePipeline:
        def predict(self, frame):
            assert frame.iloc[0]["recent_minutes_avg"] == 30.0
            assert frame.iloc[0]["pts_last5_avg"] == 20.0
            return [22.35]

    monkeypatch.setattr(predict_player.joblib, "load", lambda path: {
        "features": ["pts_season_avg", "pts_last5_avg", "pts_last10_avg", "is_home", "recent_minutes_avg"],
        "pipeline": FakePipeline(),
    })
    result = predict_player.predict([
        {"game_date": "2026-01-01", "points": 10, "minutes": 20},
        {"game_date": "2026-01-03", "points": 30, "minutes": 40},
    ])
    assert result["success"] is True
    assert result["predictedPoints"] == 22.35
