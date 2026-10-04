/**
 * Sprint 1's "first integration test" — kept minimal and focused on just
 * the health check. Player endpoint tests live in players.test.js.
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

const app = express();
app.use(healthRouter);

test("GET /health returns ok status", async () => {
  const res = await request(app).get("/health");
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.status, "ok");
});
