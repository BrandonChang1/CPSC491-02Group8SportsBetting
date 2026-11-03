"""SEC-05 tests (SCRUM-113): the prediction service reports the verified model_version.

ml/predict_player.py is the process the Express route /api/players/:id/prediction
spawns, so its JSON output is the API's model fields.
"""
import json
import subprocess
import sys
from pathlib import Path

from conftest import FIXTURE_MODEL_VERSION

from ml import predict_player
from ml.model_integrity import approved_entry, registry_file

REPO_ROOT = Path(__file__).resolve().parents[1]
GAMES = [
    {"game_date": "2026-01-01", "points": 18, "minutes": 31},
    {"game_date": "2026-01-03", "points": 24, "minutes": 35},
]


def approved_manifest():
    entry = approved_entry(predict_player.REGISTRY)
    return json.loads(registry_file(predict_player.REGISTRY, entry["manifest_path"]).read_text())


def test_prediction_reports_the_approved_manifest_model_version():
    result = predict_player.predict(GAMES)

    assert result["success"] is True
    assert result["modelVersion"] == approved_manifest()["model_version"]


def test_spawned_prediction_process_reports_the_approved_model_version():
    # Same invocation as backend/app/routes/predictions.js: the script, JSON on stdin.
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "ml" / "predict_player.py")],
        input=json.dumps({"games": GAMES}), capture_output=True, text=True, cwd=REPO_ROOT, check=True,
    )
    result = json.loads(completed.stdout)

    assert result["success"] is True
    assert result["modelVersion"] == approved_manifest()["model_version"]


def test_model_version_comes_from_the_manifest_not_the_code(approved_model, monkeypatch):
    monkeypatch.setattr(predict_player, "REGISTRY", approved_model.registry_path)

    result = predict_player.predict(GAMES)

    assert result["modelVersion"] == FIXTURE_MODEL_VERSION == approved_model.manifest["model_version"]
