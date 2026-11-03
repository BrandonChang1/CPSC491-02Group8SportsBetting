"""SEC-05 tests (SCRUM-109, SCRUM-110): save_model, the model registry, and serving the approved model.

Everything is built in tmp_path with save_model; no committed model or registry is used.
"""
import json

import pandas as pd
import pytest

from ml import model_integrity, predict_player
from ml.model_integrity import (
    MODEL_VERSION_PATTERN,
    ManifestMissingError,
    ModelArtifactMissingError,
    ModelHashMismatchError,
    MultipleApprovedModelsError,
    NoApprovedModelError,
    RegistryError,
    approved_entry,
    read_registry,
    registry_file,
    save_model,
    set_status,
    sha256_file,
    validate_manifest,
)

GAMES = [
    {"game_date": "2026-01-01", "points": 20, "minutes": 30},
    {"game_date": "2026-01-03", "points": 26, "minutes": 34},
]


def serve_from(monkeypatch, registry_path):
    monkeypatch.setattr(predict_player, "REGISTRY", registry_path)
    return predict_player.predict(GAMES)


def rewrite_registry(registry_path, change):
    registry = json.loads(registry_path.read_text())
    change(registry["models"])
    registry_path.write_text(json.dumps(registry))


# --- save_model -----------------------------------------------------------


def test_save_model_writes_a_valid_manifest_derived_from_the_model(save, approved_model):
    entry = save()
    artifact = registry_file(approved_model.registry_path, entry["artifact_path"])
    manifest = json.loads(registry_file(approved_model.registry_path, entry["manifest_path"]).read_text())

    assert validate_manifest(manifest) == []
    assert manifest["model_sha256"] == sha256_file(artifact)
    assert manifest["dataset_hash"] == sha256_file(approved_model.dataset_path)
    assert manifest["feature_schema"] == [{"name": n, "dtype": d} for n, d in predict_player.EXPECTED_FEATURE_SCHEMA]
    assert manifest["evaluation_metrics"]["test"]["MAE"] == 1.25
    assert manifest["training_config"]["estimator"] == "SimpleImputer -> LinearRegression"
    assert isinstance(manifest["training_config"]["git_worktree_clean"], bool)
    # Timestamp plus short commit, and still a version the loader accepts.
    version = MODEL_VERSION_PATTERN.match(manifest["model_version"])
    assert version and version["name"] == "random-forest-points" and version["major"] == "1"
    assert manifest["model_version"].endswith("." + manifest["git_commit_sha"][:7])


def test_save_model_appends_a_candidate_entry_and_leaves_others_alone(save, approved_model):
    before = read_registry(approved_model.registry_path)["models"]

    entry = save()

    after = read_registry(approved_model.registry_path)["models"]
    assert after[:-1] == before
    assert after[-1] == entry
    assert entry["status"] == "candidate"
    assert entry["metrics"] == {"n": 6, "MAE": 1.25, "RMSE": 1.5, "R2": 0.9}
    assert entry["created_at"] and len(entry["git_commit_sha"]) == 40
    assert approved_entry(approved_model.registry_path)["model_version"] == before[0]["model_version"]


def test_each_save_gets_its_own_files(save, approved_model, monkeypatch):
    # Two saves within the same second would collide on name, so advance the clock between them.
    ticks = iter(pd.date_range("2026-11-02 17:00:00", periods=4, freq="s", tz="UTC").to_pydatetime())

    class Clock:
        @staticmethod
        def now(tz):
            return next(ticks)

    monkeypatch.setattr(model_integrity, "datetime", Clock)
    first, second = save(), save(intercept_shift=5.0)

    assert first["artifact_path"] != second["artifact_path"]
    assert registry_file(approved_model.registry_path, first["artifact_path"]).exists()


def test_failed_save_leaves_no_files_or_entry(approved_model, training_frame, tmp_path):
    features, _ = training_frame
    before = approved_model.registry_path.read_text()

    with pytest.raises(ValueError, match="not found in dataset"):
        save_model(object(), model_name="random-forest-points", features=features.rename(columns={"is_home": "home"}),
                   dataset_path=approved_model.dataset_path, training_config={"x": 1},
                   evaluation_metrics={"test": {"MAE": 1.0}}, artifact_dir=tmp_path / "artifacts",
                   registry_path=approved_model.registry_path)

    assert list((tmp_path / "artifacts").iterdir()) == []
    assert approved_model.registry_path.read_text() == before


# --- set_status -----------------------------------------------------------


def test_approving_a_model_demotes_the_previous_one(save, approved_model):
    previous = approved_entry(approved_model.registry_path)["model_version"]
    new = save()["model_version"]

    changes = set_status(new, "approved", registry_path=approved_model.registry_path)

    assert changes == {previous: ("approved", "candidate"), new: ("candidate", "approved")}
    statuses = [entry["status"] for entry in read_registry(approved_model.registry_path)["models"]]
    assert statuses.count("approved") == 1
    assert approved_entry(approved_model.registry_path)["model_version"] == new


def test_rejecting_the_approved_model_leaves_none_approved(approved_model):
    version = approved_entry(approved_model.registry_path)["model_version"]

    set_status(version, "rejected", registry_path=approved_model.registry_path)

    with pytest.raises(NoApprovedModelError):
        approved_entry(approved_model.registry_path)


def test_set_status_rejects_unknown_versions_and_statuses(approved_model):
    with pytest.raises(RegistryError):
        set_status("random-forest-points-v9", "approved", registry_path=approved_model.registry_path)
    with pytest.raises(ValueError):
        set_status(approved_entry(approved_model.registry_path)["model_version"], "deployed",
                   registry_path=approved_model.registry_path)


def test_a_tampered_model_cannot_be_approved(save, approved_model):
    entry = save()
    artifact = registry_file(approved_model.registry_path, entry["artifact_path"])
    artifact.write_bytes(artifact.read_bytes() + b"\x00")
    before = approved_model.registry_path.read_text()

    with pytest.raises(ModelHashMismatchError):
        set_status(entry["model_version"], "approved", registry_path=approved_model.registry_path)
    assert approved_model.registry_path.read_text() == before


# --- predict_player serves only the single approved model -------------------


def test_predictor_serves_the_approved_model(save, approved_model, monkeypatch):
    new = save()
    set_status(new["model_version"], "approved", registry_path=approved_model.registry_path)

    result = serve_from(monkeypatch, approved_model.registry_path)

    assert result["success"] is True
    assert result["modelVersion"] == new["model_version"]


@pytest.mark.parametrize(("break_registry", "error"), [
    pytest.param(lambda models: models[0].update(status="rejected"), NoApprovedModelError, id="no-approved"),
    pytest.param(lambda models: models.append({**models[0], "model_version": "random-forest-points-v1.3.0"}),
                 MultipleApprovedModelsError, id="multiple-approved"),
    pytest.param(lambda models: models[0].update(manifest_path="artifacts/missing.manifest.json"),
                 ManifestMissingError, id="manifest-missing"),
    pytest.param(lambda models: models[0].update(artifact_path="artifacts/missing.joblib"),
                 ModelArtifactMissingError, id="artifact-missing"),
    pytest.param(lambda models: models[0].update(model_version="random-forest-points-v1.9.0"),
                 RegistryError, id="registry-disagrees-with-manifest"),
])
def test_predictor_fails_closed(approved_model, monkeypatch, break_registry, error):
    rewrite_registry(approved_model.registry_path, break_registry)

    result = serve_from(monkeypatch, approved_model.registry_path)

    assert result["success"] is False
    assert result["errorCode"] == error.code
    assert "predictedPoints" not in result and "modelVersion" not in result


@pytest.mark.parametrize("contents", ["{not json", '{"models": "nope"}'], ids=["unparseable", "malformed"])
def test_predictor_fails_closed_on_a_broken_registry(approved_model, monkeypatch, contents):
    approved_model.registry_path.write_text(contents)

    result = serve_from(monkeypatch, approved_model.registry_path)

    assert result["success"] is False and result["errorCode"] == RegistryError.code
    assert "predictedPoints" not in result


def test_predictor_fails_closed_without_a_registry(tmp_path, monkeypatch):
    result = serve_from(monkeypatch, tmp_path / "registry.json")

    assert result["success"] is False and result["errorCode"] == RegistryError.code


# --- The committed registry -------------------------------------------------


def test_committed_registry_has_exactly_one_approved_and_intact_models():
    registry_path = model_integrity.REGISTRY_PATH
    models = read_registry(registry_path)["models"]

    assert [entry["status"] for entry in models].count("approved") == 1
    for entry in models:
        manifest = json.loads(registry_file(registry_path, entry["manifest_path"]).read_text())
        assert manifest["model_version"] == entry["model_version"]
        assert sha256_file(registry_file(registry_path, entry["artifact_path"])) == manifest["model_sha256"]
