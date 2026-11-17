/**
 * SCRUM-137: GET /health/freshness reports fresh, stale, failed and
 * never-refreshed data from ingestion_refresh_runs.
 *
 * Requires DATABASE_URL with migrations applied (npm run migrate). Rows are
 * written for throwaway player IDs and deleted afterwards.
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const healthRouter = require("../app/routes/health");
const { errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(healthRouter);
app.use(errorHandler);

const SEASON = "2099-00";
const FRESH = 990301;
const STALE = 990302;
const FAILED_AFTER_SUCCESS = 990303;
const NEVER = 990304;
const IDS = [FRESH, STALE, FAILED_AFTER_SUCCESS, NEVER];

async function addRun(playerId, status, hoursAgo, errorType = null) {
  await pool.query(
    `INSERT INTO ingestion_refresh_runs (player_id, season, status, started_at, finished_at, error_type)
     VALUES ($1, $2, $3, now() - ($4 + 1) * INTERVAL '1 hour', now() - $4 * INTERVAL '1 hour', $5)`,
    [playerId, SEASON, status, hoursAgo, errorType]
  );
}

const freshness = (playerId) =>
  request(app).get("/health/freshness").query({ player_id: playerId, season: SEASON });

test.before(async () => {
  await pool.query("DELETE FROM ingestion_refresh_runs WHERE player_id = ANY($1)", [IDS]);
  await addRun(FRESH, "succeeded", 1);
  await addRun(STALE, "succeeded", 72);
  await addRun(FAILED_AFTER_SUCCESS, "succeeded", 10);
  await addRun(FAILED_AFTER_SUCCESS, "failed", 1, "ConnectionError");
});

test.after(async () => {
  await pool.query("DELETE FROM ingestion_refresh_runs WHERE player_id = ANY($1)", [IDS]);
  await pool.end();
});

test("recent success is fresh", async () => {
  const res = await freshness(FRESH);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.freshness, "fresh");
  assert.strictEqual(res.body.is_stale, false);
  assert.strictEqual(res.body.max_age_hours, 48);
  assert.deepStrictEqual(res.body.scope, { player_id: FRESH, season: SEASON });
});

test("success older than the threshold is stale", async () => {
  const res = await freshness(STALE);
  assert.strictEqual(res.body.freshness, "stale");
  assert.strictEqual(res.body.is_stale, true);
});

test("failed latest attempt is reported without replacing the last success", async () => {
  const res = await freshness(FAILED_AFTER_SUCCESS);
  assert.strictEqual(res.body.freshness, "failed");
  assert.strictEqual(res.body.latest_attempt.status, "failed");
  assert.strictEqual(res.body.latest_attempt.error_type, "ConnectionError");
  assert.ok(new Date(res.body.last_successful_refresh) < new Date(res.body.latest_attempt.finished_at));
});

test("scope with no attempts is never_refreshed", async () => {
  const res = await freshness(NEVER);
  assert.strictEqual(res.body.freshness, "never_refreshed");
  assert.strictEqual(res.body.latest_attempt, null);
  assert.strictEqual(res.body.last_successful_refresh, null);
});

test("threshold is configurable with DATA_FRESHNESS_MAX_AGE_HOURS", async () => {
  process.env.DATA_FRESHNESS_MAX_AGE_HOURS = "100";
  try {
    const res = await freshness(STALE);
    assert.strictEqual(res.body.freshness, "fresh");
    assert.strictEqual(res.body.max_age_hours, 100);
  } finally {
    delete process.env.DATA_FRESHNESS_MAX_AGE_HOURS;
  }
});

test("database-wide freshness needs no scope", async () => {
  const res = await request(app).get("/health/freshness");
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.scope, "database");
  assert.ok(["fresh", "stale", "failed", "running", "never_refreshed"].includes(res.body.freshness));
});

test("invalid scope is rejected", async () => {
  for (const query of [{ player_id: 1 }, { player_id: "abc", season: SEASON }, { player_id: 1, season: "2099" }]) {
    const res = await request(app).get("/health/freshness").query(query);
    assert.strictEqual(res.status, 400);
  }
});
