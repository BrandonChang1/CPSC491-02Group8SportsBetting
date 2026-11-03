"""SEC-05 tests (SCRUM-114): approval summary and rollback, on save_model fixtures in tmp_path."""
import pytest

from ml import model_release, predict_player
from ml.model_integrity import (
    ModelIntegrityError,
    approved_entry,
    read_registry,
    set_status,
)


def upgrade(save, approved_model):
    """The fixture's approved model is "previous"; a newly saved model is approved as the upgrade."""
    previous = approved_entry(approved_model.registry_path)["model_version"]
    failed = save(intercept_shift=50.0)["model_version"]
    set_status(failed, "approved", registry_path=approved_model.registry_path)
    return previous, failed


def test_rollback_restores_the_previous_model_and_verifies_the_load(save, approved_model, monkeypatch):
    previous, failed = upgrade(save, approved_model)

    result = model_release.rollback(failed, previous, approved_model.registry_path)

    statuses = {e["model_version"]: e["status"] for e in read_registry(approved_model.registry_path)["models"]}
    assert statuses[previous] == "approved" and statuses[failed] == "rejected"
    assert list(statuses.values()).count("approved") == 1
    verification = result["verification"]
    assert verification["consistent"] is True
    assert verification["loaded_model_version"] == verification["registry_approved_version"] == previous
    assert verification["manifest_model_version"] == previous
    assert result["status_changes"] == {previous: ["candidate", "approved"], failed: ["approved", "rejected"]}

    monkeypatch.setattr(predict_player, "REGISTRY", approved_model.registry_path)
    assert predict_player.predict([{"game_date": "2026-01-01", "points": 20}])["modelVersion"] == previous


def test_rollback_fails_loudly_if_the_restored_model_does_not_load(save, approved_model):
    previous, failed = upgrade(save, approved_model)
    approved_model.artifact_path.write_bytes(approved_model.artifact_path.read_bytes() + b"\x00")

    with pytest.raises(ModelIntegrityError):
        model_release.rollback(failed, previous, approved_model.registry_path)


def test_rollback_rejects_unknown_or_identical_versions(approved_model):
    current = approved_entry(approved_model.registry_path)["model_version"]
    with pytest.raises(ValueError):
        model_release.rollback(current, current, approved_model.registry_path)
    with pytest.raises(ModelIntegrityError):
        model_release.rollback("random-forest-points-v9", current, approved_model.registry_path)


def test_approval_summary_has_validation_results_and_baseline_section(save, approved_model):
    version = save()["model_version"]

    summary = model_release.summary_markdown(version, approved_model.registry_path)

    assert "### Validation results" in summary
    for check in ("Manifest complete | pass", "matches manifest SHA-256 | pass", "Loads through the secure loader"):
        assert check in summary
    assert "### Baseline comparison" in summary and "not an approval threshold" in summary


def test_approval_has_no_performance_requirement(approved_model, training_frame, tmp_path, monkeypatch):
    # A model that loses to every baseline can still be approved and served.
    from sklearn.dummy import DummyRegressor

    from ml.model_integrity import save_model

    features, target = training_frame
    worse = {"test": {"n": 6, "MAE": 99.0, "RMSE": 99.0, "R2": -5.0},
             "baselines_test": {"Last 10 avg": {"n": 6, "MAE": 1.0, "RMSE": 1.0, "R2": 0.9}},
             "best_baseline": "Last 10 avg", "beats_best_baseline": False}
    entry = save_model(DummyRegressor().fit(features, target), model_name="random-forest-points", features=features,
                       dataset_path=approved_model.dataset_path, training_config={"estimator": "dummy"},
                       evaluation_metrics=worse, artifact_dir=tmp_path / "artifacts",
                       registry_path=approved_model.registry_path)

    set_status(entry["model_version"], "approved", registry_path=approved_model.registry_path)

    monkeypatch.setattr(predict_player, "REGISTRY", approved_model.registry_path)
    assert predict_player.predict([{"game_date": "2026-01-01", "points": 20}])["modelVersion"] == entry["model_version"]
    assert "Model beats it on MAE: no" in model_release.summary_markdown(entry["model_version"], approved_model.registry_path)
