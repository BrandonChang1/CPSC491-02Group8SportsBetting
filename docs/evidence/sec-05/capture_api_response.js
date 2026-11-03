/**
 * Captures a real GET /api/players/:id/prediction response for SEC-05 evidence.
 * Only the database is stubbed; the route spawns the real ml/predict_player.py.
 *
 * Usage: PYTHON_COMMAND=<python with requirements.txt> node capture_api_response.js <repo root>
 */
const path = require("path");

const root = path.resolve(process.argv[2] || path.join(__dirname, "..", "..", ".."));
const load = (name) => require(require.resolve(name, { paths: [root] }));
const express = load("express");
const request = load("supertest");
const pool = require(path.join(root, "backend", "app", "db"));
const predictionsRouter = require(path.join(root, "backend", "app", "routes", "predictions"));

pool.query = async () => ({
  rows: [
    { game_date: "2026-01-01", points: 18, minutes: 31 },
    { game_date: "2026-01-03", points: 24, minutes: 35 },
    { game_date: "2026-01-05", points: 27, minutes: 36 },
  ],
});

const app = express().use(predictionsRouter);
request(app)
  .get("/api/players/9300001/prediction")
  .then((res) => {
    console.log(JSON.stringify({ request: "GET /api/players/9300001/prediction", status: res.status, body: res.body }, null, 2));
    return pool.end();
  });
