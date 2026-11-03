"""SEC-05 tests (SCRUM-111): manifests and verify-before-load for model artifacts.

Every test builds its own model and manifest in tmp_path (see conftest.py), so
nothing depends on the committed artifacts. Negative tests check the specific
exception, that the artifact was never deserialized, and that the prediction
code fails closed without a prediction.
"""
import re

import pytest
from conftest import FIXTURE_MODEL_VERSION, build_approved_model

from ml import model_integrity, predict_player
from ml.model_integrity import (
    REQUIRED_FIELDS,
    FeatureSchemaMismatchError,
    IncompatibleModelVersionError,
    IncompleteManifestError,
    ManifestMissingError,
    ModelHashMismatchError,
    ModelIntegrityError,
    VerifiedModel,
    load_verified_model,
    sha256_file,
    validate_manifest,
)

GAMES = [
    {"game_date": "2026-01-01", "points": 20, "minutes": 30},
    {"game_date": "2026-01-03", "points": 26, "minutes": 34},
]


def load(model):
    return load_verified_model(
        model.artifact_path,
        model_name=predict_player.MODEL_NAME,
        supported_major_versions=predict_player.SUPPORTED_MAJOR_VERSIONS,
        expected_feature_schema=predict_player.EXPECTED_FEATURE_SCHEMA,
    )


@pytest.fixture
def deserialize_calls(monkeypatch):
    """Record every joblib.load the loader makes, so tests can prove nothing was unpickled."""
    calls = []
    real_load = model_integrity.joblib.load

    def spy(source):
        calls.append(source)
        return real_load(source)

    monkeypatch.setattr(model_integrity.joblib, "load", spy)
    return calls


def assert_rejected(model, error, monkeypatch, deserialize_calls, *, deserialized=False):
    """The loader raises `error`, returns nothing, and predict() produces no prediction."""
    with pytest.raises(error) as raised:
        load(model)
    assert len(deserialize_calls) == (1 if deserialized else 0)

    monkeypatch.setattr(predict_player, "MODEL_PATH", model.artifact_path)
    result = predict_player.predict(GAMES)
    assert result["success"] is False
    assert result["errorCode"] == error.code
    assert "predictedPoints" not in result and "modelVersion" not in result
    # The client-facing message must not leak server paths or hashes.
    assert str(model.artifact_path.parent) not in result["message"]
    assert not re.search(r"[0-9a-f]{64}", result["message"])
    return raised.value


# --- Positive -------------------------------------------------------------


def test_generated_manifest_is_complete_and_hashes_the_artifact(approved_model):
    manifest = approved_model.manifest
    assert validate_manifest(manifest) == []
    assert manifest["model_sha256"] == sha256_file(approved_model.artifact_path)
    assert manifest["dataset_hash"] == sha256_file(approved_model.dataset_path)
    assert [f["name"] for f in manifest["feature_schema"]] == [n for n, _ in predict_player.EXPECTED_FEATURE_SCHEMA]


def test_approved_model_loads_and_predicts(approved_model, deserialize_calls, monkeypatch):
    model = load(approved_model)

    assert isinstance(model, VerifiedModel)
    assert model.model_version == FIXTURE_MODEL_VERSION
    assert model.manifest == approved_model.manifest
    assert len(deserialize_calls) == 1

    monkeypatch.setattr(predict_player, "MODEL_PATH", approved_model.artifact_path)
    result = predict_player.predict(GAMES)
    assert result["success"] is True
    assert isinstance(result["predictedPoints"], float)
    assert result["modelVersion"] == FIXTURE_MODEL_VERSION


# --- Modified artifact ----------------------------------------------------


@pytest.mark.parametrize("tamper", [
    pytest.param(lambda data: data[:-1] + bytes([data[-1] ^ 0x01]), id="flipped-bit"),
    pytest.param(lambda data: data + b"\x00", id="appended-byte"),
    pytest.param(lambda data: data[:-16], id="truncated"),
])
def test_modified_artifact_is_rejected_before_deserialization(approved_model, tamper, monkeypatch, deserialize_calls):
    path = approved_model.artifact_path
    path.write_bytes(tamper(path.read_bytes()))

    assert_rejected(approved_model, ModelHashMismatchError, monkeypatch, deserialize_calls)


def test_swapped_in_loadable_model_is_rejected(approved_model, monkeypatch, deserialize_calls):
    # A different, perfectly loadable bundle placed under the approved manifest.
    bundle = model_integrity.joblib.load(approved_model.artifact_path)
    bundle["pipeline"].named_steps["model"].intercept_ += 50
    model_integrity.joblib.dump(bundle, approved_model.artifact_path)
    deserialize_calls.clear()

    assert_rejected(approved_model, ModelHashMismatchError, monkeypatch, deserialize_calls)


# --- Incomplete or missing manifest ---------------------------------------


@pytest.mark.parametrize("field", list(REQUIRED_FIELDS))
def test_manifest_missing_a_required_field_is_rejected(approved_model, field, monkeypatch, deserialize_calls):
    manifest = approved_model.manifest
    del manifest[field]
    approved_model.write_manifest(manifest)

    error = assert_rejected(approved_model, IncompleteManifestError, monkeypatch, deserialize_calls)
    assert error.problems == [f"missing required field '{field}'"]


def test_incomplete_manifest_reports_every_problem(approved_model, monkeypatch, deserialize_calls):
    manifest = approved_model.manifest
    del manifest["model_sha256"]
    manifest["dataset_version"] = ""
    manifest["evaluation_metrics"] = {}
    manifest["feature_schema"][0]["dtype"] = " "
    approved_model.write_manifest(manifest)

    error = assert_rejected(approved_model, IncompleteManifestError, monkeypatch, deserialize_calls)
    assert error.problems == [
        "missing required field 'model_sha256'",
        "required field 'dataset_version' is empty",
        "required field 'evaluation_metrics' is empty",
        "feature_schema[0].dtype is missing or empty",
    ]


def test_unparseable_manifest_is_rejected(approved_model, monkeypatch, deserialize_calls):
    approved_model.manifest_path.write_text("{not json")

    assert_rejected(approved_model, IncompleteManifestError, monkeypatch, deserialize_calls)


def test_missing_manifest_is_rejected(approved_model, monkeypatch, deserialize_calls):
    approved_model.manifest_path.unlink()

    assert_rejected(approved_model, ManifestMissingError, monkeypatch, deserialize_calls)


# --- Incompatible feature schema ------------------------------------------


@pytest.mark.parametrize("change", [
    pytest.param(lambda schema: schema.reverse(), id="reordered"),
    pytest.param(lambda schema: schema[3].update(dtype="float64"), id="dtype-changed"),
    pytest.param(lambda schema: schema.pop(), id="feature-removed"),
    pytest.param(lambda schema: schema.append({"name": "rest_days", "dtype": "int64"}), id="feature-added"),
    pytest.param(lambda schema: schema[0].update(name="pts_avg"), id="feature-renamed"),
])
def test_incompatible_feature_schema_is_rejected(approved_model, change, monkeypatch, deserialize_calls):
    manifest = approved_model.manifest
    change(manifest["feature_schema"])
    approved_model.write_manifest(manifest)

    assert_rejected(approved_model, FeatureSchemaMismatchError, monkeypatch, deserialize_calls)


def test_artifact_features_disagreeing_with_manifest_are_rejected(tmp_path, monkeypatch, deserialize_calls):
    # Manifest and hash are valid, but the bundle itself was trained on a different feature order.
    features = [name for name, _ in predict_player.EXPECTED_FEATURE_SCHEMA]
    model = build_approved_model(tmp_path, monkeypatch, bundle_features=list(reversed(features)))

    assert_rejected(model, FeatureSchemaMismatchError, monkeypatch, deserialize_calls, deserialized=True)


# --- Incompatible model version -------------------------------------------


@pytest.mark.parametrize("version", [
    pytest.param("linear-regression-points-v2", id="unsupported-major"),
    pytest.param("linear-regression-points-v0.9.0", id="older-major"),
    pytest.param("random-forest-points-v1", id="different-model"),
    pytest.param("linear-regression-points-1", id="malformed"),
])
def test_incompatible_model_version_is_rejected(approved_model, version, monkeypatch, deserialize_calls):
    manifest = approved_model.manifest
    manifest["model_version"] = version
    approved_model.write_manifest(manifest)

    assert_rejected(approved_model, IncompatibleModelVersionError, monkeypatch, deserialize_calls)


# --- Supporting behaviour -------------------------------------------------


def test_every_integrity_error_has_a_distinct_code():
    errors = [ManifestMissingError, IncompleteManifestError, ModelHashMismatchError,
              IncompatibleModelVersionError, FeatureSchemaMismatchError]
    assert all(issubclass(error, ModelIntegrityError) for error in errors)
    assert len({error.code for error in errors}) == len(errors)


def test_git_commit_sha_falls_back_to_head_outside_the_repo(tmp_path):
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"x")
    assert re.fullmatch(r"[0-9a-f]{40}", model_integrity.git_commit_sha(artifact))
