/**
 * Sprint 2 backend tests: player search, player details, player game
 * history, pagination, and consistent error handling (US-4/US-5, plus
 * the CI/CD plan's "API error-handling tests" and "Sprint 2 endpoint
 * tests" work items).
 *
 * Seeds a small, clearly-fake set of rows (ids in the 9000000s so they
 * can't collide with real ingested NBA data) before the tests run, and
 * removes them afterward — so this suite is safe to run repeatedly
 * against a shared dev database, and works from a clean CI database too.
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

const pool = require("../app/db");
const playersRouter = require("../app/routes/players");
const { notFoundHandler, errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(playersRouter);
app.use(notFoundHandler);
app.use(errorHandler);

// Fake, clearly-out-of-range ids so this suite never collides with real
// ingested NBA data (real NBA player/team/game ids don't reach this range).
const TEAM_ID = 9000001;
const RIVAL_TEAM_ID = 9000002; // games has CHECK (home_team_id <> away_team_id)
const PLAYER_ID = 9000001;
const OTHER_PLAYER_ID = 9000002; // has no team, no games — edge case coverage
const GAME_ID_OLD = "9000001";
const GAME_ID_NEW = "9000002";

test.before(async () => {
  await pool.query(
    `INSERT INTO teams (id, full_name, abbreviation, city)
     VALUES
       ($1, 'Test City Testers', 'TST', 'Test City'),
       ($2, 'Test City Rivals', 'RIV', 'Test City')
     ON CONFLICT (id) DO NOTHING`,
    [TEAM_ID, RIVAL_TEAM_ID]
  );

  await pool.query(
    `INSERT INTO players (id, full_name, first_name, last_name, is_active, team_id)
     VALUES ($1, 'Zaphod Testington', 'Zaphod', 'Testington', true, $2)
     ON CONFLICT (id) DO NOTHING`,
    [PLAYER_ID, TEAM_ID]
  );

  await pool.query(
    `INSERT INTO players (id, full_name, first_name, last_name, is_active, team_id)
     VALUES ($1, 'Solo Testerson', 'Solo', 'Testerson', true, NULL)
     ON CONFLICT (id) DO NOTHING`,
    [OTHER_PLAYER_ID]
  );

  await pool.query(
    `INSERT INTO games (id, game_date, home_team_id, away_team_id)
     VALUES
       ($1, '2025-01-01', $3, $4),
       ($2, '2025-01-10', $3, $4)
     ON CONFLICT (id) DO NOTHING`,
    [GAME_ID_OLD, GAME_ID_NEW, TEAM_ID, RIVAL_TEAM_ID]
  );

  await pool.query(
    `INSERT INTO player_game_stats (player_id, game_id, minutes, points, rebounds, assists, matchup, win_loss)
     VALUES
       ($1, $2, 30, 20, 5, 4, 'TST vs. RIV', 'W'),
       ($1, $3, 34, 27, 6, 7, 'TST @ RIV', 'L')
     ON CONFLICT (player_id, game_id) DO NOTHING`,
    [PLAYER_ID, GAME_ID_OLD, GAME_ID_NEW]
  );
});

test.after(async () => {
  await pool.query("DELETE FROM player_game_stats WHERE player_id = $1", [PLAYER_ID]);
  await pool.query("DELETE FROM games WHERE id IN ($1, $2)", [GAME_ID_OLD, GAME_ID_NEW]);
  await pool.query("DELETE FROM players WHERE id IN ($1, $2)", [PLAYER_ID, OTHER_PLAYER_ID]);
  await pool.query("DELETE FROM teams WHERE id IN ($1, $2)", [TEAM_ID, RIVAL_TEAM_ID]);
  await pool.end();
});

// --- GET /players (list + search) ------------------------------------

test("GET /players returns an array", async () => {
  const res = await request(app).get("/players");
  assert.strictEqual(res.status, 200);
  assert.ok(Array.isArray(res.body));
});

test("GET /players?search= finds a player by partial, case-insensitive name", async () => {
  const res = await request(app).get("/players?search=zaphod");
  assert.strictEqual(res.status, 200);
  const found = res.body.find((p) => p.id === PLAYER_ID);
  assert.ok(found, "expected seeded player to appear in search results");
  assert.strictEqual(found.full_name, "Zaphod Testington");
});

test("GET /players?search= with no match returns an empty array, not an error", async () => {
  const res = await request(app).get("/players?search=nonexistent-xyz-123");
  assert.strictEqual(res.status, 200);
  assert.deepStrictEqual(res.body, []);
});

test("GET /players?limit=500 is rejected with a consistent error shape", async () => {
  const res = await request(app).get("/players?limit=500");
  assert.strictEqual(res.status, 400);
  assert.ok(res.body.error && typeof res.body.error.message === "string");
});

test("GET /players?skip=-1 is rejected", async () => {
  const res = await request(app).get("/players?skip=-1");
  assert.strictEqual(res.status, 400);
});

// --- GET /players/:id (details) ---------------------------------------

test("GET /players/:id returns player details joined with team info", async () => {
  const res = await request(app).get(`/players/${PLAYER_ID}`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.full_name, "Zaphod Testington");
  assert.strictEqual(res.body.team_abbreviation, "TST");
});

test("GET /players/:id works when the player has no team (null join)", async () => {
  const res = await request(app).get(`/players/${OTHER_PLAYER_ID}`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.team_id, null);
});

test("GET /players/:id returns 404 for an unknown id", async () => {
  const res = await request(app).get("/players/999999999");
  assert.strictEqual(res.status, 404);
  assert.ok(res.body.error && typeof res.body.error.message === "string");
});

test("GET /players/:id rejects a non-numeric id with 400, not 500", async () => {
  const res = await request(app).get("/players/not-a-number");
  assert.strictEqual(res.status, 400);
});

// --- GET /players/:id/games (game history) ----------------------------

test("GET /players/:id/games returns games newest first", async () => {
  const res = await request(app).get(`/players/${PLAYER_ID}/games`);
  assert.strictEqual(res.status, 200);
  assert.ok(Array.isArray(res.body));
  assert.strictEqual(res.body.length, 2);
  assert.strictEqual(res.body[0].game_id, GAME_ID_NEW); // Jan 10 before Jan 1
  assert.strictEqual(res.body[0].points, 27);
});

test("GET /players/:id/games respects limit", async () => {
  const res = await request(app).get(`/players/${PLAYER_ID}/games?limit=1`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.length, 1);
});

test("GET /players/:id/games 404s for a player that doesn't exist", async () => {
  const res = await request(app).get("/players/999999999/games");
  assert.strictEqual(res.status, 404);
});
