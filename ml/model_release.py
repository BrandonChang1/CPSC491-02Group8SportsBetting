"""Model approval and rollback helpers (SEC-05, SCRUM-114). Process: docs/model_release_process.md.

    python ml/model_release.py summary VERSION              # approval PR body: validation + baseline comparison
    python ml/model_release.py rollback FAILED PREVIOUS     # reject FAILED, restore PREVIOUS, verify the load
    python ml/model_release.py verify                       # which model the predictor loads now

Statuses only change through ml.model_integrity.set_status. The baseline
comparison is reported for reviewers; approval does not require beating it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import predict_player  # noqa: E402
from ml.model_integrity import (  # noqa: E402
    REGISTRY_PATH,
    ModelIntegrityError,
    approved_entry,
    load_approved_model,
    load_verified_model,
    read_registry,
    registry_file,
    set_status,
    sha256_file,
    validate_manifest,
)

SERVING_REQUIREMENTS = {
    "model_name": predict_player.MODEL_NAME,
    "supported_major_versions": predict_player.SUPPORTED_MAJOR_VERSIONS,
    "expected_feature_schema": predict_player.EXPECTED_FEATURE_SCHEMA,
}


def _entry(version, registry_path):
    for entry in read_registry(registry_path)["models"]:
        if entry["model_version"] == version:
            return entry
    raise ModelIntegrityError(f"{version} is not in the registry")


def validate(version, registry_path=REGISTRY_PATH):
    """The validation results an approval PR must show for one registered model."""
    entry = _entry(version, registry_path)
    manifest_path = registry_file(registry_path, entry["manifest_path"])
    artifact_path = registry_file(registry_path, entry["artifact_path"])
    manifest = json.loads(manifest_path.read_text())
    try:
        load_verified_model(artifact_path, manifest_path=manifest_path, **SERVING_REQUIREMENTS)
        servable = "pass"
    except ModelIntegrityError as exc:
        servable = f"FAIL ({exc.code})"
    return {
        "entry": entry,
        "manifest": manifest,
        "manifest_problems": validate_manifest(manifest),
        "hash_matches": sha256_file(artifact_path) == manifest["model_sha256"],
        "registry_matches_manifest": entry["model_version"] == manifest["model_version"],
        "servable": servable,
    }


def summary_markdown(version, registry_path=REGISTRY_PATH):
    result = validate(version, registry_path)
    entry, manifest = result["entry"], result["manifest"]
    metrics, config = manifest["evaluation_metrics"], manifest["training_config"]

    def check(ok):
        return "pass" if ok else "FAIL"

    lines = [
        f"## Model approval: `{version}`",
        "",
        (f"- Current status: `{entry['status']}` · created {entry['created_at']} · commit `{manifest['git_commit_sha'][:7]}`"
        f" (worktree clean: {config.get('git_worktree_clean', 'not recorded')})"),
        f"- Model SHA-256 `{manifest['model_sha256']}`",
        f"- Dataset `{manifest['dataset_version']}` (SHA-256 `{manifest['dataset_hash'][:12]}…`)",
        "",
        "### Validation results",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Manifest complete | {check(not result['manifest_problems'])} {'; '.join(result['manifest_problems'])} |",
        f"| Model file matches manifest SHA-256 | {check(result['hash_matches'])} |",
        f"| Registry entry matches manifest version | {check(result['registry_matches_manifest'])} |",
        f"| Loads through the secure loader with the predictor's version and feature schema | {result['servable']} |",
        "",
        "### Baseline comparison (same held-out rows; informational, not an approval threshold)",
        "",
    ]
    holdout = config.get("holdout", {}).get("test")
    if holdout:
        lines += [(f"Held-out period: {holdout['first_game']} → {holdout['last_game']}, "
                  f"{holdout['rows']} rows, {holdout['players']} players."), ""]
    test = metrics.get("test", {})
    baselines = metrics.get("baselines_test")
    lines += ["| Model / baseline | n | MAE | RMSE | R² |", "|---|---|---|---|---|"]
    lines.append(f"| **{version}** | {test.get('n', '-')} | {test.get('MAE', '-')} | {test.get('RMSE', '-')} | {test.get('R2', '-')} |")
    if baselines:
        for name, values in baselines.items():
            lines.append(f"| {name} | {values['n']} | {values['MAE']} | {values['RMSE']} | {values['R2']} |")
        lines += ["", (f"Best baseline: {metrics.get('best_baseline')}. "
                      f"Model beats it on MAE: {'yes' if metrics.get('beats_best_baseline') else 'no'}.")]
    else:
        lines += ["", "No baseline comparison is recorded in this model's manifest."]
    return "\n".join(lines) + "\n"


def verify(registry_path=REGISTRY_PATH):
    """Load the approved model exactly as the predictor does and cross-check every source of its version."""
    model = load_approved_model(registry_path=registry_path, **SERVING_REQUIREMENTS)
    entry = approved_entry(registry_path)
    manifest = json.loads(registry_file(registry_path, entry["manifest_path"]).read_text())
    artifact_sha = sha256_file(registry_file(registry_path, entry["artifact_path"]))
    return {
        "loaded_model_version": model.model_version,
        "registry_approved_version": entry["model_version"],
        "manifest_model_version": manifest["model_version"],
        "manifest_model_sha256": manifest["model_sha256"],
        "artifact_sha256": artifact_sha,
        "consistent": model.model_version == entry["model_version"] == manifest["model_version"]
        and artifact_sha == manifest["model_sha256"],
    }


def rollback(failed, previous, registry_path=REGISTRY_PATH):
    """Restore `previous` and reject `failed`, then verify the predictor loads `previous`.

    `previous` is approved first, so there is never a moment with no approved model.
    """
    if failed == previous:
        raise ValueError("The failed and previous versions must differ")
    _entry(failed, registry_path)

    def statuses():
        return {entry["model_version"]: entry["status"] for entry in read_registry(registry_path)["models"]}

    before = statuses()
    set_status(previous, "approved", registry_path=registry_path)
    set_status(failed, "rejected", registry_path=registry_path)
    after = statuses()
    verification = verify(registry_path)
    if not (verification["consistent"] and verification["loaded_model_version"] == previous):
        raise ModelIntegrityError(f"Rollback verification failed: {verification}")
    changes = {version: [before[version], after[version]] for version in after if before.get(version) != after[version]}
    return {"status_changes": changes, "verification": verification}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("summary").add_argument("version")
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("failed")
    rollback_parser.add_argument("previous")
    commands.add_parser("verify")

    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            print(summary_markdown(args.version, args.registry), end="")
        elif args.command == "rollback":
            print(json.dumps(rollback(args.failed, args.previous, args.registry), indent=2))
        else:
            result = verify(args.registry)
            print(json.dumps(result, indent=2))
            return 0 if result["consistent"] else 1
    except (OSError, ValueError, ModelIntegrityError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
