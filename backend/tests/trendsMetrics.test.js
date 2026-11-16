/**
 * Sprint 5 tests (SCRUM-72): GET /players/:id/trends.
 *
 * Covers the trend calculation (up / down / short history / no games), the
 * limit parameter, the unknown-player 404, bad input (400), the shared error
 * shape, and that the route requires a login session.
 *
 * Seeds clearly-fake rows (ids in the 9200000s, distinct from the other test
 * files because node:test runs files in parallel against the same database)
 * and removes them afterward. A fake user and session are seeded so requests
 * can be authenticated.
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const crypto = require("crypto");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const playersRouter = require("../app/routes/players");
const { router: authRouter } = require("../app/routes/auth");
const { notFoundHandler, errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(express.json());
app.use(authRouter);
app.use(playersRouter);
app.use(notFoundHandler);
app.use(errorHandler);

const TEAM_ID = 9200001;
const RIVAL_TEAM_ID = 9200002;
const UP_PLAYER_ID = 9200001; // 10 games: first five 10 pts, last five 20 pts
const DOWN_PLAYER_ID = 9200002; // 10 games: first five 20 pts, last five 10 pts
const SHORT_PLAYER_ID = 9200003; // 3 games: not enough for a "previous" window
const NO_GAMES_PLAYER_ID = 9200004; // exists, but has no games
const PLAYER_IDS = [UP_PLAYER_ID, DOWN_PLAYER_ID, SHORT_PLAYER_ID, NO_GAMES_PLAYER_ID];

// Oldest -> newest.
const UP_HISTORY = [10, 10, 10, 10, 10, 20, 20, 20, 20, 20];
const DOWN_HISTORY = [20, 20, 20, 20, 20, 10, 10, 10, 10, 10];
const SHORT_HISTORY = [12, 14, 16];

const ids = (start, count) => Array.from({ length: count }, (_, i) => String(start + i));
const UP_GAME_IDS = ids(9200001, UP_HISTORY.length);
const DOWN_GAME_IDS = ids(9200101, DOWN_HISTORY.length);
const SHORT_GAME_IDS = ids(9200201, SHORT_HISTORY.length);

// --- authentication fixtures --------------------------------------------
// A fake user plus a login session. Only the SHA-256 hash of the cookie
// value is stored, the same way the real login route does it.
const USER_NAME = "scrum72_trends_user";
const USER_EMAIL = "scrum72_trends_user@example.com";
const RAW_TOKEN = crypto.randomBytes(32).toString("hex");
const COOKIE = `nba_session=${RAW_TOKEN}`;
const hashToken = (token) => crypto.createHash("sha256").update(token).digest("hex");
let userId;

/** GET with a valid session cookie. */
const authedGet = (url) => request(app).get(url).set("Cookie", COOKIE);

async function cleanupUser() {
  await pool.query(
    "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE username = $1)",
    [USER_NAME]
  );
  await pool.query("DELETE FROM users WHERE username = $1", [USER_NAME]);
}

/** Seeds one game per entry (oldest first) on consecutive days of the given month. */
async function seedGames(playerId, gameIds, pointsOldestFirst, month) {
  for (let i = 0; i < gameIds.length; i++) {
    const date = `2025-${month}-${String(i + 1).padStart(2, "0")}`;
    await pool.query(
      `INSERT INTO games (id, game_date, home_team_id, away_team_id)
       VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING`,
      [gameIds[i], date, TEAM_ID, RIVAL_TEAM_ID]
    );
    await pool.query(
      `INSERT INTO player_game_stats (player_id, game_id, minutes, points, rebounds, assists, matchup, win_loss)
       VALUES ($1, $2, 30, $3, 5, 4, 'TST vs. RIV', 'W') ON CONFLICT (player_id, game_id) DO NOTHING`,
      [playerId, gameIds[i], pointsOldestFirst[i]]
    );
  }
}

test.before(async () => {
  await pool.query(
    `INSERT INTO teams (id, full_name, abbreviation, city)
     VALUES ($1, 'Trend City Testers', 'TCT', 'Trend City'),
            ($2, 'Trend City Rivals', 'TCR', 'Trend City')
     ON CONFLICT (id) DO NOTHING`,
    [TEAM_ID, RIVAL_TEAM_ID]
  );
  await pool.query(
    `INSERT INTO players (id, full_name, first_name, last_name, is_active, team_id)
     VALUES ($1, 'Rising Ray', 'Rising', 'Ray', true, $5),
            ($2, 'Falling Fred', 'Falling', 'Fred', true, $5),
            ($3, 'Shorty Trend', 'Shorty', 'Trend', true, $5),
            ($4, 'Newcomer Trendless', 'Newcomer', 'Trendless', true, $5)
     ON CONFLICT (id) DO NOTHING`,
    [UP_PLAYER_ID, DOWN_PLAYER_ID, SHORT_PLAYER_ID, NO_GAMES_PLAYER_ID, TEAM_ID]
  );
  await seedGames(UP_PLAYER_ID, UP_GAME_IDS, UP_HISTORY, "02");
  await seedGames(DOWN_PLAYER_ID, DOWN_GAME_IDS, DOWN_HISTORY, "03");
  await seedGames(SHORT_PLAYER_ID, SHORT_GAME_IDS, SHORT_HISTORY, "04");

  // Fake user + valid session (cleans up leftovers from an earlier failed run first).
  await cleanupUser();
  const user = await pool.query(
    `INSERT INTO users (username, email, password_hash)
     VALUES ($1, $2, 'scrypt:test:test') RETURNING id`,
    [USER_NAME, USER_EMAIL]
  );
  userId = user.rows[0].id;
  await pool.query(
    `INSERT INTO user_sessions (user_id, token_hash, expires_at)
     VALUES ($1, $2, NOW() + INTERVAL '1 day')`,
    [userId, hashToken(RAW_TOKEN)]
  );
});

test.after(async () => {
  const gameIds = [...UP_GAME_IDS, ...DOWN_GAME_IDS, ...SHORT_GAME_IDS];
  await cleanupUser();
  await pool.query("DELETE FROM player_game_stats WHERE player_id = ANY($1)", [PLAYER_IDS]);
  await pool.query("DELETE FROM games WHERE id = ANY($1)", [gameIds]);
  await pool.query("DELETE FROM players WHERE id = ANY($1)", [PLAYER_IDS]);
  await pool.query("DELETE FROM teams WHERE id IN ($1, $2)", [TEAM_ID, RIVAL_TEAM_ID]);
  await pool.end();
});

// --- GET /players/:id/trends ---------------------------------------------

test("GET /players/:id/trends reports an upward trend with the correct averages", async () => {
  const res = await authedGet(`/players/${UP_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.player_id, UP_PLAYER_ID);
  assert.strictEqual(res.body.games_analyzed, 10);
  assert.strictEqual(res.body.recent_average, 20);
  assert.strictEqual(res.body.previous_average, 10);
  assert.strictEqual(res.body.change, 10);
  assert.strictEqual(res.body.direction, "up");
});

test("GET /players/:id/trends reports a downward trend", async () => {
  const res = await authedGet(`/players/${DOWN_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.recent_average, 10);
  assert.strictEqual(res.body.previous_average, 20);
  assert.strictEqual(res.body.change, -10);
  assert.strictEqual(res.body.direction, "down");
});

test("trends lists the games oldest first with their points", async () => {
  const res = await authedGet(`/players/${UP_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 200);
  assert.deepStrictEqual(
    res.body.games.map((g) => g.points),
    UP_HISTORY
  );
  const dates = res.body.games.map((g) => g.game_date);
  assert.deepStrictEqual(dates, [...dates].sort(), "games must be in date order, oldest first");
});

test("trends respects the limit parameter", async () => {
  const res = await authedGet(`/players/${UP_PLAYER_ID}/trends?limit=3`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.games_analyzed, 3);
  assert.deepStrictEqual(
    res.body.games.map((g) => g.points),
    [20, 20, 20],
    "limit keeps the newest games"
  );
  assert.strictEqual(res.body.previous_average, null, "no earlier window when only 3 games are analyzed");
  assert.strictEqual(res.body.direction, null);
});

test("a player with fewer than 10 games still gets recent data but no direction", async () => {
  const res = await authedGet(`/players/${SHORT_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.games_analyzed, 3);
  assert.strictEqual(res.body.recent_average, 14);
  assert.strictEqual(res.body.previous_average, null);
  assert.strictEqual(res.body.change, null);
  assert.strictEqual(res.body.direction, null);
});

test("a player with no games returns 200 with an empty trend, not an error", async () => {
  const res = await authedGet(`/players/${NO_GAMES_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.games_analyzed, 0);
  assert.deepStrictEqual(res.body.games, []);
  assert.strictEqual(res.body.recent_average, null);
  assert.strictEqual(res.body.direction, null);
});

test("trends returns 404 with the shared error shape for an unknown player", async () => {
  const res = await authedGet("/players/9299999/trends");
  assert.strictEqual(res.status, 404);
  assert.deepStrictEqual(res.body, { error: { message: "Player not found" } });
});

test("trends rejects a non-numeric player id with 400, not 500", async () => {
  const res = await authedGet("/players/abc/trends");
  assert.strictEqual(res.status, 400);
  assert.ok(res.body.error && typeof res.body.error.message === "string");
});

test("trends rejects an invalid limit with 400", async () => {
  for (const bad of ["0", "-1", "abc", "500"]) {
    const res = await authedGet(`/players/${UP_PLAYER_ID}/trends?limit=${bad}`);
    assert.strictEqual(res.status, 400, `limit=${bad} should be rejected`);
    assert.ok(res.body.error && typeof res.body.error.message === "string");
  }
});

// --- authentication (SEC-02) ---------------------------------------------

test("trends without a session cookie returns 401 and no data", async () => {
  const res = await request(app).get(`/players/${UP_PLAYER_ID}/trends`);
  assert.strictEqual(res.status, 401);
  assert.strictEqual(res.body.games, undefined, "no trend data may leak to an anonymous caller");
});

test("trends with an invalid session cookie returns 401", async () => {
  const res = await request(app)
    .get(`/players/${UP_PLAYER_ID}/trends`)
    .set("Cookie", `nba_session=${crypto.randomBytes(32).toString("hex")}`);
  assert.strictEqual(res.status, 401);
});