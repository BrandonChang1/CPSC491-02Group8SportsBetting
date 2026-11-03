"""Shared fixtures: a small trained model and approved manifest built in tmp_path."""
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

from ml import model_integrity, predict_player

FIXTURE_MODEL_VERSION = "linear-regression-points-v1.2.0"
FIXTURE_COMMIT = "0" * 40


@dataclass
class ApprovedModel:
    artifact_path: Path
    manifest_path: Path
    dataset_path: Path

    @property
    def manifest(self):
        return json.loads(self.manifest_path.read_text())

    def write_manifest(self, manifest):
        self.manifest_path.write_text(json.dumps(manifest))


def build_approved_model(directory, monkeypatch, *, bundle_features=None):
    """Train a tiny pipeline on predict_player's features, save it, and approve it with a manifest."""
    features = [name for name, _ in predict_player.EXPECTED_FEATURE_SCHEMA]
    data = pd.DataFrame({
        "pts_season_avg": [10.0, 15.0, 20.0, 25.0, 30.0, 12.0],
        "pts_last5_avg": [11.0, 14.0, 21.0, 24.0, 29.0, 13.0],
        "pts_last10_avg": [10.5, 15.5, 19.5, 25.5, 30.5, 12.5],
        "is_home": [1, 0, 1, 0, 1, 0],
        "recent_minutes_avg": [20.0, 25.0, 30.0, 33.0, 36.0, 22.0],
        "points": [11, 15, 21, 24, 31, 12],
    })
    dataset_path = directory / "train.csv"
    data.to_csv(dataset_path, index=False)

    pipeline = Pipeline([("impute", SimpleImputer(strategy="median")), ("model", LinearRegression())])
    pipeline.fit(data[features], data["points"])
    artifact_path = directory / "points_model.joblib"
    joblib.dump({"pipeline": pipeline, "features": bundle_features or features, "target": "points"}, artifact_path)

    # Keep the fixture independent of the checkout's git state.
    monkeypatch.setattr(model_integrity, "git_commit_sha", lambda path: FIXTURE_COMMIT)
    manifest = model_integrity.generate_manifest(
        artifact_path,
        model_version=FIXTURE_MODEL_VERSION,
        dataset_path=dataset_path,
        feature_schema=[{"name": name, "dtype": dtype} for name, dtype in predict_player.EXPECTED_FEATURE_SCHEMA],
        training_config={"estimator": "SimpleImputer -> LinearRegression", "target": "points"},
        evaluation_metrics={"train": {"n": len(data), "MAE": 0.5}},
    )
    manifest_path = model_integrity.write_manifest(artifact_path, manifest)
    return ApprovedModel(artifact_path, manifest_path, dataset_path)


@pytest.fixture
def approved_model(tmp_path, monkeypatch):
    return build_approved_model(tmp_path, monkeypatch)
