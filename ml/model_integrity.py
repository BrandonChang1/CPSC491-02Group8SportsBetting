"""Model version manifests and verify-before-load for trained model artifacts.

Every joblib artifact in ml/models/artifacts/ has a manifest next to it
(<artifact stem>.manifest.json) recording the artifact's SHA-256, the dataset
and code it came from, its ordered feature schema, config and metrics.

load_verified_model() is the only supported way to load an artifact: it checks
the manifest and artifact bytes BEFORE anything is deserialized, because
joblib/pickle can run arbitrary code on load.

Generate a manifest for an existing artifact:
    python ml/model_integrity.py generate ARTIFACT --model-version NAME-vN \
        --dataset CSV --feature-schema name:dtype,... --config JSON --metrics CSV
"""
import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 1024 * 1024

# Required manifest fields and the JSON type each must have.
REQUIRED_FIELDS = {
    "model_version": str,
    "model_sha256": str,
    "dataset_version": str,
    "dataset_hash": str,
    "git_commit_sha": str,
    "feature_schema": list,
    "training_config": dict,
    "evaluation_metrics": dict,
}

# e.g. "linear-regression-points-v1" or "linear-regression-points-v1.2.0"
MODEL_VERSION_PATTERN = re.compile(r"^(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)-v(?P<major>\d+)(?:\.\d+){0,2}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ModelIntegrityError(Exception):
    """Base class: the artifact failed verification and must not be used."""


class ManifestMissingError(ModelIntegrityError):
    """No manifest file exists for the artifact."""


class IncompleteManifestError(ModelIntegrityError):
    """The manifest is unreadable or has missing, empty or malformed fields."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("Model manifest is incomplete: " + "; ".join(self.problems))


class ModelHashMismatchError(ModelIntegrityError):
    """The artifact bytes do not match the manifest's model_sha256."""


class IncompatibleModelVersionError(ModelIntegrityError):
    """The manifest's model_version is not one this code supports."""


class FeatureSchemaMismatchError(ModelIntegrityError):
    """The model's feature schema differs from what the prediction code sends."""


@dataclass(frozen=True)
class VerifiedModel:
    """A deserialized artifact that passed verification, plus its manifest."""

    artifact: Any
    manifest: dict
    model_version: str


def manifest_path_for(artifact_path):
    artifact_path = Path(artifact_path)
    return artifact_path.with_name(f"{artifact_path.stem}.manifest.json")


def sha256_file(path):
    """SHA-256 of a file, read in chunks so large artifacts are not held in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit_sha(artifact_path):
    """Commit the artifact came from.

    A committed, unmodified artifact maps to the last commit that changed it, so
    manifests for already-trained models point at the code that produced them.
    A new or modified artifact maps to HEAD.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()

    path = str(Path(artifact_path).resolve())
    if not git("status", "--porcelain", "--", path):
        last_change = git("log", "-1", "--format=%H", "--", path)
        if last_change:
            return last_change
    return git("rev-parse", "HEAD")


def parse_feature_schema(spec):
    """'a:float64,b:int64' -> [{'name': 'a', 'dtype': 'float64'}, ...]"""
    schema = []
    for item in spec.split(","):
        name, _, dtype = item.strip().partition(":")
        schema.append({"name": name.strip(), "dtype": dtype.strip()})
    return schema


def load_metrics(path):
    """Read a metrics file: JSON as-is, or a notebook metrics CSV keyed by its split column."""
    path = Path(path)
    if path.suffix == ".json":
        return json.loads(path.read_text())
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    def number(value):
        try:
            return int(value)
        except ValueError:
            return float(value)

    return {row.pop("split"): {key: number(value) for key, value in row.items() if key != "model"} for row in rows}


def _is_empty(value):
    return value is None or (isinstance(value, (str, list, dict)) and not (value.strip() if isinstance(value, str) else value))


def validate_manifest(manifest):
    """Return every problem with the manifest (an empty list means it is complete)."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]

    problems = []
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in manifest:
            problems.append(f"missing required field '{field}'")
        elif _is_empty(manifest[field]):
            problems.append(f"required field '{field}' is empty")
        elif not isinstance(manifest[field], expected_type):
            problems.append(f"field '{field}' must be a {expected_type.__name__}")

    for field, pattern in (("model_sha256", SHA256_PATTERN), ("dataset_hash", SHA256_PATTERN), ("git_commit_sha", GIT_SHA_PATTERN)):
        value = manifest.get(field)
        if isinstance(value, str) and value and not pattern.match(value):
            problems.append(f"field '{field}' is not a valid hex digest")

    schema = manifest.get("feature_schema")
    if isinstance(schema, list):
        for index, feature in enumerate(schema):
            if not isinstance(feature, dict):
                problems.append(f"feature_schema[{index}] must be an object with 'name' and 'dtype'")
                continue
            for key in ("name", "dtype"):
                if _is_empty(feature.get(key)) or not isinstance(feature.get(key), str):
                    problems.append(f"feature_schema[{index}].{key} is missing or empty")
    return problems


def generate_manifest(artifact_path, *, model_version, dataset_path, feature_schema, training_config,
                      evaluation_metrics, dataset_version=None):
    """Build a manifest for an artifact; raises IncompleteManifestError if any field is missing."""
    artifact_path = Path(artifact_path)
    dataset_path = Path(dataset_path)
    dataset_hash = sha256_file(dataset_path)

    with open(dataset_path, newline="") as handle:
        columns = set(next(csv.reader(handle), []))
    absent = [feature["name"] for feature in feature_schema if feature["name"] not in columns]
    if absent:
        raise ValueError(f"Features not found in dataset {dataset_path}: {absent}")

    manifest = {
        "model_version": model_version,
        "model_sha256": sha256_file(artifact_path),
        # Defaults to the repo's dataset convention: file name plus first 12 hash characters.
        "dataset_version": dataset_version or f"{dataset_path.stem}_{dataset_hash[:12]}",
        "dataset_hash": dataset_hash,
        "git_commit_sha": git_commit_sha(artifact_path),
        "feature_schema": feature_schema,
        "training_config": training_config,
        "evaluation_metrics": evaluation_metrics,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    problems = validate_manifest(manifest)
    if problems:
        raise IncompleteManifestError(problems)
    if not MODEL_VERSION_PATTERN.match(model_version):
        raise ValueError(f"model_version '{model_version}' must look like 'name-v1' or 'name-v1.2.3'")
    return manifest


def write_manifest(artifact_path, manifest):
    path = manifest_path_for(artifact_path)
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def verify_manifest(manifest, *, model_name, supported_major_versions, expected_feature_schema):
    """Check a parsed manifest against what the calling code supports. Touches no artifact bytes."""
    problems = validate_manifest(manifest)
    if problems:
        raise IncompleteManifestError(problems)

    version = MODEL_VERSION_PATTERN.match(manifest["model_version"])
    if not version or version["name"] != model_name or int(version["major"]) not in supported_major_versions:
        supported = ", ".join(f"{model_name}-v{major}" for major in sorted(supported_major_versions))
        raise IncompatibleModelVersionError(
            f"Model version '{manifest['model_version']}' is not supported (expected {supported})"
        )

    actual = [(feature["name"], feature["dtype"]) for feature in manifest["feature_schema"]]
    expected = [tuple(feature) for feature in expected_feature_schema]
    if actual != expected:
        raise FeatureSchemaMismatchError(f"Model feature schema {actual} does not match prediction inputs {expected}")


def load_verified_model(artifact_path, *, model_name, supported_major_versions, expected_feature_schema,
                        manifest_path=None):
    """Verify an artifact against its manifest, then deserialize it.

    All checks run before deserialization. The artifact is read once and the
    verified bytes are what gets loaded, so the file cannot be swapped between
    hashing and loading. Raises a ModelIntegrityError subclass on any failure.
    """
    artifact_path = Path(artifact_path)
    manifest_path = Path(manifest_path) if manifest_path else manifest_path_for(artifact_path)

    try:
        manifest = json.loads(manifest_path.read_text())
    except FileNotFoundError:
        raise ManifestMissingError(f"No manifest found at {manifest_path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IncompleteManifestError([f"manifest {manifest_path} could not be read: {exc}"]) from None

    verify_manifest(manifest, model_name=model_name, supported_major_versions=supported_major_versions,
                    expected_feature_schema=expected_feature_schema)

    digest = hashlib.sha256()
    buffer = io.BytesIO()
    with open(artifact_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            buffer.write(chunk)
    if digest.hexdigest() != manifest["model_sha256"]:
        raise ModelHashMismatchError(
            f"SHA-256 of {artifact_path.name} ({digest.hexdigest()}) does not match manifest ({manifest['model_sha256']})"
        )

    buffer.seek(0)
    artifact = joblib.load(buffer)

    # The bundle's own feature list must agree with the verified manifest too.
    bundled = artifact.get("features") if isinstance(artifact, dict) else None
    if bundled is not None and list(bundled) != [feature["name"] for feature in manifest["feature_schema"]]:
        raise FeatureSchemaMismatchError(f"Artifact features {list(bundled)} do not match its manifest")

    return VerifiedModel(artifact=artifact, manifest=manifest, model_version=manifest["model_version"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="write <artifact>.manifest.json for a trained artifact")
    generate.add_argument("artifact", type=Path)
    generate.add_argument("--model-version", required=True)
    generate.add_argument("--dataset", required=True, type=Path)
    generate.add_argument("--dataset-version")
    generate.add_argument("--feature-schema", required=True, help="ordered name:dtype pairs, comma-separated")
    generate.add_argument("--config", required=True, help="training config as a JSON string or JSON file path")
    generate.add_argument("--metrics", required=True, type=Path, help="metrics CSV (with a split column) or JSON")

    check = commands.add_parser("check", help="report every problem with an existing manifest")
    check.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            config_path = Path(args.config)
            config = json.loads(config_path.read_text() if config_path.suffix == ".json" and config_path.exists() else args.config)
            manifest = generate_manifest(
                args.artifact,
                model_version=args.model_version,
                dataset_path=args.dataset,
                dataset_version=args.dataset_version,
                feature_schema=parse_feature_schema(args.feature_schema),
                training_config=config,
                evaluation_metrics=load_metrics(args.metrics),
            )
            print(f"Wrote {write_manifest(args.artifact, manifest)}")
        else:
            problems = validate_manifest(json.loads(args.manifest.read_text()))
            for problem in problems:
                print(f"- {problem}")
            print("Manifest is complete" if not problems else f"{len(problems)} problem(s) found")
            return 1 if problems else 0
    except (OSError, ValueError, ModelIntegrityError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
