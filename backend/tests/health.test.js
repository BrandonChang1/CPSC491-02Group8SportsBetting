/**
 * Sprint 1's "first integration test" (Person 5 coordinates CI overall, but
 * this lives in backend/tests since it tests your endpoints specifically).
 *
 * Run with: npm test
 * Requires DATABASE_URL (in .env) to point at a running Postgres instance
 * with migrations applied (npm run migrate).
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const healthRouter = require("../app/routes/health");
const playersRouter = require("../app/routes/players");

const app = express();
app.use(healthRouter);
app.use(playersRouter);

test("GET /health returns ok status", async () => {
  const res = await request(app).get("/health");
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.status, "ok");
});

test("GET /players returns an array", async () => {
  const res = await request(app).get("/players");
  assert.strictEqual(res.status, 200);
  assert.ok(Array.isArray(res.body));
});

test("GET /players?limit=500 is rejected", async () => {
  const res = await request(app).get("/players?limit=500");
  assert.strictEqual(res.status, 400);
});

test("GET /players/:id returns 404 for an unknown id", async () => {
  const res = await request(app).get("/players/999999999");
  assert.strictEqual(res.status, 404);
});
