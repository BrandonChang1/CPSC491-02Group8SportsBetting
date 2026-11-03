/**
 * SEC-05 backend test (SCRUM-113): GET /api/players/:id/prediction reports
 * the model_version from the approved manifest of the model it used.
 *
 * Only the database is stubbed; the route spawns the real ml/predict_player.py,
 * which loads the committed model through the verify-before-load loader. Needs
 * a Python with requirements.txt installed (PYTHON_COMMAND, default python3).
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const predictionsRouter = require("../app/routes/predictions");

const MANIFEST_PATH = path.join(__dirname, "..", "..", "ml", "models", "artifacts", "random_forest_points.manifest.json");
const GAMES = [
  { game_date: "2026-01-01", points: 18, minutes: 31 },
  { game_date: "2026-01-03", points: 24, minutes: 35 },
  { game_date: "2026-01-05", points: 27, minutes: 36 },
];

const app = express();
app.use(predictionsRouter);

test.before(() => {
  test.mock.method(pool, "query", async () => ({ rows: GAMES }));
});

test.after(async () => {
  test.mock.restoreAll();
  await pool.end();
});

test("GET /api/players/:id/prediction returns the approved manifest's model_version", async () => {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));

  const res = await request(app).get("/api/players/9300001/prediction");

  assert.strictEqual(res.status, 200, JSON.stringify(res.body));
  assert.strictEqual(res.body.success, true);
  assert.strictEqual(res.body.source, "database");
  assert.strictEqual(typeof res.body.predictedPoints, "number");
  assert.strictEqual(res.body.modelVersion, manifest.model_version);
});
