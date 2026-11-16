/**
 * Sprint 5 tests (SCRUM-72): GET /models/metrics.
 *
 * Covers the real registry response, the shape (and that internal details such
 * as commit hashes and file paths are not exposed), models without metrics,
 * the "no metrics available yet" 404 (missing file and empty registry), a
 * corrupt registry (500 with the shared error shape and no internals leaked),
 * and that the route requires a login session.
 *
 * The edge cases point the service at a temporary registry file, so nothing in
 * ml/models/registry.json is touched. A fake user and session are seeded so
 * requests can be authenticated, and removed afterward.
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const os = require("os");
const fs = require("fs/promises");
const crypto = require("crypto");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const predictionsRouter = require("../app/routes/predictions");
const { router: authRouter } = require("../app/routes/auth");
const modelMetrics = require("../app/services/modelMetrics");
const { notFoundHandler, errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(express.json());
app.use(authRouter);
app.use(predictionsRouter);
app.use(notFoundHandler);
app.use(errorHandler);

// --- authentication fixtures --------------------------------------------
const USER_NAME = "scrum72_metrics_user";
const USER_EMAIL = "scrum72_metrics_user@example.com";
const RAW_TOKEN = crypto.randomBytes(32).toString("hex");
const COOKIE = `nba_session=${RAW_TOKEN}`;
const hashToken = (token) => crypto.createHash("sha256").update(token).digest("hex");

const authedGet = (url) => request(app).get(url).set("Cookie", COOKIE);

async function cleanupUser() {
  await pool.query(
    "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE username = $1)",
    [USER_NAME]
  );
  await pool.query("DELETE FROM users WHERE username = $1", [USER_NAME]);
}

// --- temporary registry helpers -----------------------------------------
const REAL_REGISTRY_PATH = modelMetrics.source.registryPath;
const tempFiles = [];

/** Points the service at a temp registry. Pass null for a path with no file. */
async function useRegistry(contents) {
  const file = path.join(os.tmpdir(), `scrum72_registry_${process.pid}_${tempFiles.length}.json`);
  tempFiles.push(file);
  if (contents !== null) await fs.writeFile(file, contents);
  modelMetrics.source.registryPath = file;
}

test.before(async () => {
  await cleanupUser();
  const user = await pool.query(
    `INSERT INTO users (username, email, password_hash)
     VALUES ($1, $2, 'scrypt:test:test') RETURNING id`,
    [USER_NAME, USER_EMAIL]
  );
  await pool.query(
    `INSERT INTO user_sessions (user_id, token_hash, expires_at)
     VALUES ($1, $2, NOW() + INTERVAL '1 day')`,
    [user.rows[0].id, hashToken(RAW_TOKEN)]
  );
});

test.afterEach(() => {
  modelMetrics.source.registryPath = REAL_REGISTRY_PATH;
});

test.after(async () => {
  await cleanupUser();
  for (const file of tempFiles) await fs.rm(file, { force: true });
  await pool.end();
});

// --- the real registry ----------------------------------------------------

test("GET /models/metrics returns metrics for the models in the real registry", async () => {
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 200);
  assert.ok(Array.isArray(res.body.models) && res.body.models.length > 0, "expected at least one model");

  for (const m of res.body.models) {
    assert.strictEqual(typeof m.model_version, "string");
    assert.strictEqual(typeof m.status, "string");
    assert.ok(m.metrics, `${m.model_version} should have metrics`);
    assert.strictEqual(typeof m.metrics.MAE, "number");
    assert.strictEqual(typeof m.metrics.RMSE, "number");
  }

  const approved = res.body.models.find((m) => m.status === "approved");
  if (approved) {
    assert.strictEqual(res.body.approved_model_version, approved.model_version);
  }
});

test("the response does not expose commit hashes or file paths", async () => {
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 200);
  const text = JSON.stringify(res.body);
  for (const field of ["git_commit_sha", "artifact_path", "manifest_path", "model_sha256"]) {
    assert.ok(!text.includes(field), `${field} must not be returned`);
  }
});

// --- edge cases with a temporary registry -------------------------------

test("a model without metrics is listed with metrics null, and the approved version is reported", async () => {
  await useRegistry(
    JSON.stringify({
      models: [
        { model_version: "m-old", status: "candidate", created_at: "2026-10-01T00:00:00Z" },
        {
          model_version: "m-new",
          status: "approved",
          created_at: "2026-11-01T00:00:00Z",
          git_commit_sha: "abc123",
          artifact_path: "artifacts/x.joblib",
          metrics: { n: 100, MAE: 5.5, RMSE: 7.25, R2: 0.5 },
        },
      ],
    })
  );
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.approved_model_version, "m-new");
  assert.strictEqual(res.body.models.length, 2);
  assert.strictEqual(res.body.models[0].metrics, null);
  assert.deepStrictEqual(res.body.models[1].metrics, { n: 100, MAE: 5.5, RMSE: 7.25, R2: 0.5 });
});

test("when no model is approved, approved_model_version is null", async () => {
  await useRegistry(
    JSON.stringify({ models: [{ model_version: "m1", status: "candidate", metrics: { n: 1, MAE: 1, RMSE: 1, R2: 0 } }] })
  );
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.approved_model_version, null);
});

test("an empty registry returns 404 'No model metrics available yet'", async () => {
  await useRegistry(JSON.stringify({ models: [] }));
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 404);
  assert.deepStrictEqual(res.body, { error: { message: "No model metrics available yet" } });
});

test("a missing registry file returns the same 404, not a 500", async () => {
  await useRegistry(null);
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 404);
  assert.deepStrictEqual(res.body, { error: { message: "No model metrics available yet" } });
});

test("a corrupt registry returns 500 with the shared error shape and leaks nothing", async () => {
  await useRegistry("{ this is not valid json");
  const res = await authedGet("/models/metrics");
  assert.strictEqual(res.status, 500);
  assert.deepStrictEqual(res.body, { error: { message: "Internal server error" } });
});

// --- authentication (SEC-02) ---------------------------------------------

test("metrics without a session cookie returns 401 and no data", async () => {
  const res = await request(app).get("/models/metrics");
  assert.strictEqual(res.status, 401);
  assert.strictEqual(res.body.models, undefined, "no metrics may leak to an anonymous caller");
});

test("metrics with an invalid session cookie returns 401", async () => {
  const res = await request(app)
    .get("/models/metrics")
    .set("Cookie", `nba_session=${crypto.randomBytes(32).toString("hex")}`);
  assert.strictEqual(res.status, 401);
});  