/**
 * Sprint 3 backend tests (SCRUM-68): GET /players/:id/prediction.
 *
 * Covers the success response (predicted points, recent average, model
 * version), the unknown-player 404, and correct handling when the model
 * layer is unavailable or returns malformed output. The model failure
 * cases swap a failing `model.predict` in for the real one, so they don't
 * depend on anything external.
 *
 * Seeds clearly-fake rows (ids in the 9100000s, distinct from the
 * players.test.js range because node:test runs files in parallel against
 * the same database) and removes them afterward.
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const playersRouter = require("../app/routes/players");
const { model } = require("../app/services/prediction");
const { notFoundHandler, errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(playersRouter);
app.use(notFoundHandler);
app.use(errorHandler);

const TEAM_ID = 9100001;
const RIVAL_TEAM_ID = 9100002;
const PLAYER_ID = 9100001; // 7 games: last-5 avg (24) differs from overall avg (20)
const SHORT_PLAYER_ID = 9100002; // 2 games: fewer than the 5-game window
const NO_GAMES_PLAYER_ID = 9100003; // exists, but has no games

// Oldest -> newest. Last 5 = 20,22,24,26,28 (avg 24); all 7 avg 20.
const LONG_HISTORY = [10, 10, 20, 22, 24, 26, 28];
const SHORT_HISTORY = [10, 20]; // avg 15
const LONG_GAME_IDS = LONG_HISTORY.map((_, i) => String(9100001 + i));
const SHORT_GAME_IDS = SHORT_HISTORY.map((_, i) => String(9100101 + i));

async function seedGames(playerId, gameIds, pointsOldestFirst, firstDay) {
  for (let i = 0; i < gameIds.length; i++) {
    const date = `2025-02-${String(firstDay + i).padStart(2, "0")}`;
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
     VALUES ($1, 'Predict City Testers', 'PRT', 'Predict City'),
            ($2, 'Predict City Rivals', 'PRV', 'Predict City')
     ON CONFLICT (id) DO NOTHING`,
    [TEAM_ID, RIVAL_TEAM_ID]
  );
  await pool.query(
    `INSERT INTO players (id, full_name, first_name, last_name, is_active, team_id)
     VALUES ($1, 'Pat Predictable', 'Pat', 'Predictable', true, $4),
            ($2, 'Shorty Sample', 'Shorty', 'Sample', true, $4),
            ($3, 'Newcomer Nogames', 'Newcomer', 'Nogames', true, $4)
     ON CONFLICT (id) DO NOTHING`,
    [PLAYER_ID, SHORT_PLAYER_ID, NO_GAMES_PLAYER_ID, TEAM_ID]
  );
  await seedGames(PLAYER_ID, LONG_GAME_IDS, LONG_HISTORY, 1);
  await seedGames(SHORT_PLAYER_ID, SHORT_GAME_IDS, SHORT_HISTORY, 20);
});

test.after(async () => {
  const playerIds = [PLAYER_ID, SHORT_PLAYER_ID, NO_GAMES_PLAYER_ID];
  const gameIds = [...LONG_GAME_IDS, ...SHORT_GAME_IDS];
  await pool.query("DELETE FROM player_game_stats WHERE player_id = ANY($1)", [playerIds]);
  await pool.query("DELETE FROM games WHERE id = ANY($1)", [gameIds]);
  await pool.query("DELETE FROM players WHERE id = ANY($1)", [playerIds]);
  await pool.query("DELETE FROM teams WHERE id IN ($1, $2)", [TEAM_ID, RIVAL_TEAM_ID]);
  await pool.end();
});

/** Runs `fn` with model.predict replaced, restoring it (and silencing the expected error log) afterward. */
async function withModel(predict, fn) {
  const originalPredict = model.predict;
  const originalConsoleError = console.error;
  model.predict = predict;
  console.error = () => {};
  try {
    await fn();
  } finally {
    model.predict = originalPredict;
    console.error = originalConsoleError;
  }
}

function assertErrorShape(res) {
  assert.ok(res.body.error && typeof res.body.error.message === "string", "expected { error: { message } }");
}

// --- success ------------------------------------------------------------

test("GET /players/:id/prediction returns predicted points, averages, and model version", async () => {
  const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.player_id, PLAYER_ID);
  assert.strictEqual(res.body.player_name, "Pat Predictable");
  assert.strictEqual(res.body.predicted_points, 24);
  assert.strictEqual(res.body.recent_points_avg, 24);
  assert.strictEqual(res.body.season_points_avg, 20);
  assert.strictEqual(res.body.games_used, 7);
  assert.ok(typeof res.body.model_version === "string" && res.body.model_version.length > 0);
});

test("prediction is based on the 5 most recent games, not the oldest", async () => {
  const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
  // If the oldest 5 (10,10,20,22,24) were used this would be 17.2.
  assert.notStrictEqual(res.body.predicted_points, 17.2);
  assert.strictEqual(res.body.predicted_points, 24);
});

test("a player with fewer than 5 games still gets a prediction from the games they have", async () => {
  const res = await request(app).get(`/players/${SHORT_PLAYER_ID}/prediction`);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.predicted_points, 15);
  assert.strictEqual(res.body.games_used, 2);
});

// --- not found / bad input ---------------------------------------------

test("GET /players/:id/prediction returns 404 for an unknown player", async () => {
  const res = await request(app).get("/players/999999999/prediction");
  assert.strictEqual(res.status, 404);
  assertErrorShape(res);
});

test("GET /players/:id/prediction rejects a non-numeric id with 400", async () => {
  const res = await request(app).get("/players/not-a-number/prediction");
  assert.strictEqual(res.status, 400);
  assertErrorShape(res);
});

test("a player with no game history returns 422, not a made-up prediction", async () => {
  const res = await request(app).get(`/players/${NO_GAMES_PLAYER_ID}/prediction`);
  assert.strictEqual(res.status, 422);
  assertErrorShape(res);
});

// --- model unavailable / malformed output ------------------------------

test("returns 503 with the shared error shape when the model throws", async () => {
  await withModel(
    () => {
      throw new Error("model file missing");
    },
    async () => {
      const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
      assert.strictEqual(res.status, 503);
      assertErrorShape(res);
      assert.ok(!res.body.error.message.includes("model file missing"), "internal error text must not leak");
    }
  );
});

for (const [label, badOutput] of [
  ["undefined", undefined],
  ["an empty object", {}],
  ["a string instead of a number", { predicted_points: "24" }],
  ["NaN", { predicted_points: NaN }],
  ["Infinity", { predicted_points: Infinity }],
  ["a negative number", { predicted_points: -3 }],
]) {
  test(`returns 502 when the model output is malformed (${label})`, async () => {
    await withModel(
      () => badOutput,
      async () => {
        const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
        assert.strictEqual(res.status, 502);
        assertErrorShape(res);
      }
    );
  });
}

test("the endpoint recovers after a model failure (no stuck state)", async () => {
  await withModel(
    () => {
      throw new Error("boom");
    },
    async () => {
      const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
      assert.strictEqual(res.status, 503);
    }
  );
  const res = await request(app).get(`/players/${PLAYER_ID}/prediction`);
  assert.strictEqual(res.status, 200);
});
