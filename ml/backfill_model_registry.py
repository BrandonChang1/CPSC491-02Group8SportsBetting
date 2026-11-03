"""One-time: create ml/models/registry.json from the manifests that predate the registry.

Run once from the repository root: python ml/backfill_model_registry.py
It reads the existing manifests (it never writes one) and registers each model.
The model that ml/predict_player.py served through MODEL_PATH before the
registry existed becomes "approved"; every other model becomes "candidate".
Refuses to run if the registry already exists.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.model_integrity import ARTIFACT_DIR, REGISTRY_PATH, register_model  # noqa: E402

# predict_player.MODEL_PATH before the registry replaced it.
PREVIOUSLY_SERVED = ARTIFACT_DIR / "random_forest_points.joblib"


def main():
    if REGISTRY_PATH.exists():
        print(f"{REGISTRY_PATH} already exists; the backfill only runs once.", file=sys.stderr)
        return 1
    manifests = sorted(ARTIFACT_DIR.glob("*.manifest.json"))
    if PREVIOUSLY_SERVED.with_name(f"{PREVIOUSLY_SERVED.stem}.manifest.json") not in manifests:
        print(f"No manifest for the previously served model {PREVIOUSLY_SERVED.name}", file=sys.stderr)
        return 1
    for manifest in manifests:
        artifact = manifest.with_name(manifest.name.replace(".manifest.json", ".joblib"))
        status = "approved" if artifact == PREVIOUSLY_SERVED else "candidate"
        entry = register_model(artifact, status=status, registry_path=REGISTRY_PATH)
        print(f"{entry['status']:<9} {entry['model_version']}  ({entry['artifact_path']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
