"""SEC-05 rollback drill (SCRUM-114) against throwaway fixtures; prints the evidence as JSON.

Run from the repository root: python docs/evidence/sec-05/run_rollback_drill.py
Builds two models with save_model in a temporary directory (never the real
registry), approves A, upgrades to B, treats B as a failed upgrade, rolls back
with ml.model_release.rollback, and serves a prediction through predict_player.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ml import model_release, predict_player  # noqa: E402
from ml.model_integrity import read_registry, registry_file, save_model, set_status  # noqa: E402


def fixture_data(directory):
    data = pd.DataFrame({
        "pts_season_avg": [10.0, 15.0, 20.0, 25.0, 30.0, 12.0],
        "pts_last5_avg": [11.0, 14.0, 21.0, 24.0, 29.0, 13.0],
        "pts_last10_avg": [10.5, 15.5, 19.5, 25.5, 30.5, 12.5],
        "is_home": [True, False, True, False, True, False],
        "recent_minutes_avg": [20.0, 25.0, 30.0, 33.0, 36.0, 22.0],
        "points": [11, 15, 21, 24, 31, 12],
    })
    path = directory / "fixture_train.csv"
    data.to_csv(path, index=False)
    return data, path


def save_fixture(data, dataset_path, artifact_dir, registry_path, label, shift):
    features = data[[name for name, _ in predict_player.EXPECTED_FEATURE_SCHEMA]]
    pipeline = Pipeline([("impute", SimpleImputer(strategy="median")), ("model", LinearRegression())])
    pipeline.fit(features, data["points"] + shift)
    return save_model(
        pipeline, model_name=predict_player.MODEL_NAME, features=features, dataset_path=dataset_path,
        training_config={"fixture": label, "estimator": "SimpleImputer -> LinearRegression"},
        evaluation_metrics={"test": {"n": len(data), "MAE": 0.0, "RMSE": 0.0, "R2": 1.0}},
        artifact_dir=artifact_dir, registry_path=registry_path,
    )


def main():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        registry = directory / "registry.json"
        data, dataset_path = fixture_data(directory)
        previous = save_fixture(data, dataset_path, directory / "artifacts", registry, "A (previous approved)", 0.0)
        # Distinct timestamps give distinct versions; wait out the one-second resolution.
        time.sleep(1.1)
        failed = save_fixture(data, dataset_path, directory / "artifacts", registry, "B (failed upgrade)", 50.0)

        set_status(previous["model_version"], "approved", registry_path=registry)
        set_status(failed["model_version"], "approved", registry_path=registry)  # the upgrade
        before = model_release.verify(registry)

        result = model_release.rollback(failed["model_version"], previous["model_version"], registry)

        predict_player.REGISTRY = registry
        prediction = predict_player.predict([{"game_date": "2026-01-01", "points": 20, "minutes": 30}])
        restored = next(e for e in read_registry(registry)["models"] if e["model_version"] == previous["model_version"])
        manifest = json.loads(registry_file(registry, restored["manifest_path"]).read_text())
        evidence = {
            "fixtures_created_with": "ml.model_integrity.save_model",
            "previous_model": previous["model_version"],
            "failed_upgrade": failed["model_version"],
            "loaded_before_rollback": before["loaded_model_version"],
            "rollback": result,
            "registry_after": [{k: e[k] for k in ("model_version", "status")} for e in read_registry(registry)["models"]],
            "checks": {
                "loaded_equals_restored_registry_entry": result["verification"]["loaded_model_version"] == restored["model_version"],
                "loaded_equals_restored_manifest": result["verification"]["loaded_model_version"] == manifest["model_version"],
                "artifact_hash_equals_manifest": result["verification"]["artifact_sha256"] == manifest["model_sha256"],
                "prediction_api_model_version_equals_restored": prediction.get("modelVersion") == previous["model_version"],
            },
            "prediction_after_rollback": {k: prediction.get(k) for k in ("success", "modelVersion", "predictedPoints")},
        }
    print(json.dumps(evidence, indent=2))
    return 0 if all(evidence["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
