"""Model version manifests, the model registry, and verify-before-load.

Every joblib artifact in ml/models/artifacts/ has a manifest next to it
(<artifact stem>.manifest.json) recording the artifact's SHA-256, the dataset
and code it came from, its ordered feature schema, config and metrics.

save_model() is the only way to create a model file, its manifest and its
registry entry; nothing here is written by hand. ml/models/registry.json lists
every model with a status (candidate, approved, rejected). Exactly one model
may be approved, and set_status() is how that changes.

load_verified_model() is the only supported way to load an artifact: it checks
the manifest and artifact bytes BEFORE anything is deserialized, because
joblib/pickle can run arbitrary code on load. load_approved_model() picks the
registry's approved model and loads it through load_verified_model().

    python ml/model_integrity.py list
    python ml/model_integrity.py set-status VERSION approved|rejected|candidate
    python ml/model_integrity.py check MANIFEST
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "ml" / "models" / "artifacts"
REGISTRY_PATH = REPO_ROOT / "ml" / "models" / "registry.json"
STATUSES = ("candidate", "approved", "rejected")
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

# e.g. "random-forest-points-v1", "random-forest-points-v1.2.0", or as save_model
# names them, "random-forest-points-v1+20261102T170000Z.b03bc82" (UTC time, commit).
MODEL_VERSION_PATTERN = re.compile(
    r"^(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)-v(?P<major>\d+)(?:\.\d+){0,2}(?:\+[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ModelIntegrityError(Exception):
    """Base class: the artifact failed verification and must not be used."""

    # Stable, client-safe identifier for the failure (messages may contain paths).
    code = "model_integrity_error"


class ManifestMissingError(ModelIntegrityError):
    """No manifest file exists for the artifact."""

    code = "manifest_missing"


class IncompleteManifestError(ModelIntegrityError):
    """The manifest is unreadable or has missing, empty or malformed fields."""

    code = "manifest_incomplete"

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("Model manifest is incomplete: " + "; ".join(self.problems))


class ModelHashMismatchError(ModelIntegrityError):
    """The artifact bytes do not match the manifest's model_sha256."""

    code = "hash_mismatch"


class IncompatibleModelVersionError(ModelIntegrityError):
    """The manifest's model_version is not one this code supports."""

    code = "incompatible_model_version"


class FeatureSchemaMismatchError(ModelIntegrityError):
    """The model's feature schema differs from what the prediction code sends."""

    code = "feature_schema_mismatch"


class RegistryError(ModelIntegrityError):
    """The registry is missing, unreadable, or inconsistent with a model's manifest."""

    code = "registry_invalid"


class NoApprovedModelError(RegistryError):
    """No registry entry has status "approved"."""

    code = "no_approved_model"


class MultipleApprovedModelsError(RegistryError):
    """More than one registry entry has status "approved"."""

    code = "multiple_approved_models"


class ModelArtifactMissingError(ModelIntegrityError):
    """The registry points at a model file that does not exist."""

    code = "artifact_missing"


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
    A new, modified or out-of-repo artifact maps to HEAD.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()

    path = str(Path(artifact_path).resolve())
    try:
        if not git("status", "--porcelain", "--", path):
            last_change = git("log", "-1", "--format=%H", "--", path)
            if last_change:
                return last_change
    except subprocess.CalledProcessError:
        pass  # path is outside the repository
    return git("rev-parse", "HEAD")


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
        raise ValueError(f"model_version '{model_version}' must look like 'name-v1', 'name-v1.2.3' or 'name-v1+build'")
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




# --- Registry -------------------------------------------------------------


def read_registry(registry_path=REGISTRY_PATH):
    registry_path = Path(registry_path)
    try:
        registry = json.loads(registry_path.read_text())
    except FileNotFoundError:
        raise RegistryError(f"No model registry at {registry_path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"Model registry {registry_path} could not be read: {exc}") from None
    if not isinstance(registry, dict) or not isinstance(registry.get("models"), list):
        raise RegistryError(f"Model registry {registry_path} must be an object with a 'models' list")
    return registry


def _write_registry(registry, registry_path):
    registry_path = Path(registry_path)
    temporary = registry_path.with_name(f".{registry_path.name}.tmp")
    temporary.write_text(json.dumps(registry, indent=2) + "\n")
    os.replace(temporary, registry_path)


def registry_file(registry_path, relative):
    """Resolve a path stored in the registry (relative to the registry's folder)."""
    return Path(registry_path).parent / relative


def approved_entry(registry_path=REGISTRY_PATH):
    """The single approved registry entry; raises if there are none or several."""
    approved = [entry for entry in read_registry(registry_path)["models"] if entry.get("status") == "approved"]
    if not approved:
        raise NoApprovedModelError("No model in the registry has status 'approved'")
    if len(approved) > 1:
        versions = ", ".join(entry.get("model_version", "?") for entry in approved)
        raise MultipleApprovedModelsError(f"More than one model is approved: {versions}")
    return approved[0]


def register_model(artifact_path, *, status="candidate", registry_path=REGISTRY_PATH):
    """Add an intact artifact and its manifest to the registry; returns the new entry.

    Only save_model and the one-time backfill call this. The entry is built from
    the manifest, so registry and manifest cannot disagree when written.
    """
    artifact_path, registry_path = Path(artifact_path), Path(registry_path)
    manifest_path = manifest_path_for(artifact_path)
    manifest = json.loads(manifest_path.read_text())
    problems = validate_manifest(manifest)
    if problems:
        raise IncompleteManifestError(problems)
    if sha256_file(artifact_path) != manifest["model_sha256"]:
        raise ModelHashMismatchError(f"{artifact_path.name} does not match its manifest; not registering it")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, got {status!r}")

    registry = read_registry(registry_path) if registry_path.exists() else {"models": []}
    versions = [entry.get("model_version") for entry in registry["models"]]
    if manifest["model_version"] in versions:
        raise RegistryError(f"{manifest['model_version']} is already registered")
    if status == "approved" and any(entry.get("status") == "approved" for entry in registry["models"]):
        raise MultipleApprovedModelsError("Another model is already approved; use set_status to change approval")

    test_metrics = manifest["evaluation_metrics"].get("test", {})
    entry = {
        "model_version": manifest["model_version"],
        "status": status,
        "created_at": manifest.get("generated_at"),
        "git_commit_sha": manifest["git_commit_sha"],
        "metrics": {key: test_metrics[key] for key in ("n", "MAE", "RMSE", "R2") if key in test_metrics},
        "manifest_path": Path(os.path.relpath(manifest_path, registry_path.parent)).as_posix(),
        "artifact_path": Path(os.path.relpath(artifact_path, registry_path.parent)).as_posix(),
    }
    registry["models"].append(entry)
    _write_registry(registry, registry_path)
    return entry


def set_status(version, status, *, registry_path=REGISTRY_PATH):
    """Change a model's status. Approving one demotes the previously approved model to candidate.

    Returns {version: (old_status, new_status)} for every entry that changed.
    Approval requires the model's file and manifest to exist and match.
    """
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, got {status!r}")
    registry = read_registry(registry_path)
    matches = [entry for entry in registry["models"] if entry.get("model_version") == version]
    if not matches:
        raise RegistryError(f"{version} is not in the registry")
    target = matches[0]

    changes = {}
    if status == "approved":
        manifest_path = registry_file(registry_path, target["manifest_path"])
        artifact_path = registry_file(registry_path, target["artifact_path"])
        if not manifest_path.exists():
            raise ManifestMissingError(f"Cannot approve {version}: no manifest at {manifest_path}")
        if not artifact_path.exists():
            raise ModelArtifactMissingError(f"Cannot approve {version}: no model file at {artifact_path}")
        if sha256_file(artifact_path) != json.loads(manifest_path.read_text()).get("model_sha256"):
            raise ModelHashMismatchError(f"Cannot approve {version}: model file does not match its manifest")
        for entry in registry["models"]:
            if entry is not target and entry.get("status") == "approved":
                changes[entry["model_version"]] = ("approved", "candidate")
                entry["status"] = "candidate"

    if target["status"] != status:
        changes[version] = (target["status"], status)
        target["status"] = status
    _write_registry(registry, registry_path)
    return changes


def save_model(model, *, model_name, features, dataset_path, training_config, evaluation_metrics,
               major_version=1, artifact_dir=ARTIFACT_DIR, registry_path=REGISTRY_PATH):
    """Write a trained model, its manifest and a "candidate" registry entry; returns the entry.

    `features` is the training feature frame: its column order and dtypes become
    the feature schema. The version is "<model_name>-v<major>+<UTC timestamp>.<short commit>",
    and every save gets its own file, so earlier models stay available for rollback.
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    commit = git_commit_sha(artifact_dir / f"{model_name}_{timestamp}.joblib")
    model_version = f"{model_name}-v{major_version}+{timestamp}.{commit[:7]}"
    artifact_path = artifact_dir / f"{model_name}_{timestamp}_{commit[:7]}.joblib"
    if artifact_path.exists() or manifest_path_for(artifact_path).exists():
        raise FileExistsError(f"{artifact_path} already exists")

    feature_schema = [{"name": str(name), "dtype": str(dtype)} for name, dtype in features.dtypes.items()]
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    try:
        joblib.dump({"features": [feature["name"] for feature in feature_schema], "pipeline": model}, artifact_path)
        manifest = generate_manifest(
            artifact_path,
            model_version=model_version,
            dataset_path=dataset_path,
            feature_schema=feature_schema,
            # Records whether the commit fully describes the code that trained the model.
            training_config={**training_config, "git_worktree_clean": not dirty},
            evaluation_metrics=evaluation_metrics,
        )
        write_manifest(artifact_path, manifest)
        return register_model(artifact_path, status="candidate", registry_path=registry_path)
    except BaseException:
        artifact_path.unlink(missing_ok=True)
        manifest_path_for(artifact_path).unlink(missing_ok=True)
        raise


def load_approved_model(*, model_name, supported_major_versions, expected_feature_schema, registry_path=REGISTRY_PATH):
    """Load the registry's single approved model through load_verified_model, or raise."""
    entry = approved_entry(registry_path)
    artifact_path = registry_file(registry_path, entry["artifact_path"])
    if not artifact_path.exists():
        raise ModelArtifactMissingError(f"Approved model file {artifact_path} does not exist")
    model = load_verified_model(
        artifact_path,
        manifest_path=registry_file(registry_path, entry["manifest_path"]),
        model_name=model_name,
        supported_major_versions=supported_major_versions,
        expected_feature_schema=expected_feature_schema,
    )
    if model.model_version != entry["model_version"]:
        raise RegistryError(
            f"Registry approves {entry['model_version']} but its manifest is {model.model_version}"
        )
    return model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="show every registered model and its status")

    status = commands.add_parser("set-status", help="approve, reject or demote a registered model")
    status.add_argument("version")
    status.add_argument("status", choices=STATUSES)

    check = commands.add_parser("check", help="report every problem with an existing manifest")
    check.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for entry in read_registry(args.registry)["models"]:
                metrics = entry.get("metrics", {})
                print(f"{entry['status']:<9} {entry['model_version']:<55} {(entry.get('created_at') or '')[:19]:<19} "
                      f"{entry['git_commit_sha'][:7]}  test MAE {metrics.get('MAE', '-')}")
        elif args.command == "set-status":
            changes = set_status(args.version, args.status, registry_path=args.registry)
            for version, (old, new) in changes.items():
                print(f"{version}: {old} -> {new}")
            if not changes:
                print(f"{args.version} is already {args.status}")
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
