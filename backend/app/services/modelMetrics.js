/**
 * Reads evaluation metrics for the trained models from the model registry
 * (ml/models/registry.json), which the training scripts keep up to date.
 *
 * Only the fields a client needs are returned. The registry also holds git
 * commit hashes and file paths, which are deliberately not exposed.
 *
 * `source.registryPath` is exposed so tests can point the service at a
 * temporary registry file instead of the real one.
 */
const fs = require("fs/promises");
const path = require("path");

const source = {
  registryPath: path.join(__dirname, "..", "..", "..", "ml", "models", "registry.json"),
};

/**
 * Returns [{ model_version, status, created_at, metrics }] for every model in
 * the registry. `metrics` is { n, MAE, RMSE, R2 } or null if the model has none.
 * A missing registry file is treated as "no models yet" (empty list); a file
 * that exists but is not valid JSON is a real fault and throws.
 */
async function getModelMetrics() {
  let raw;
  try {
    raw = await fs.readFile(source.registryPath, "utf8");
  } catch (err) {
    if (err.code === "ENOENT") return [];
    throw err;
  }

  const registry = JSON.parse(raw); // a corrupt registry throws and becomes a 500
  const models = registry && Array.isArray(registry.models) ? registry.models : [];

  return models.map((m) => ({
    model_version: m.model_version,
    status: m.status,
    created_at: m.created_at,
    metrics:
      m.metrics && typeof m.metrics === "object"
        ? { n: m.metrics.n, MAE: m.metrics.MAE, RMSE: m.metrics.RMSE, R2: m.metrics.R2 }
        : null,
  }));
}

module.exports = { getModelMetrics, source };