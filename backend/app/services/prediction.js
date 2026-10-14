/**
 * Prediction service (Sprint 3): turns a player's game history into a
 * next-game points prediction.
 *
 * The model is the Sprint 1 baseline — the player's last-5-games points
 * average (docs/prediction_sprint1.md). It lives behind a small
 * `model.predict(features)` interface so a trained model can replace it
 * later without touching the route, and so tests can swap in a failing
 * or misbehaving model to exercise the error handling.
 */
const pool = require("../db");
const {
  NotFoundError,
  InsufficientDataError,
  ModelUnavailableError,
  ModelOutputError,
} = require("../errors");

const RECENT_WINDOW = 5;

const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length;
const round1 = (n) => Math.round(n * 10) / 10;

/** Baseline model: predict the last-5-games points average. */
const model = {
  version: "baseline-last5-v1",
  predict(features) {
    return { predicted_points: features.recent_points_avg };
  },
};

/** Runs the model and rejects anything that isn't a finite, non-negative number. */
function runModel(features) {
  let output;
  try {
    output = model.predict(features);
  } catch (err) {
    console.error("Prediction model failed:", err);
    throw new ModelUnavailableError("Prediction model is currently unavailable");
  }

  const points = output && output.predicted_points;
  if (typeof points !== "number" || !Number.isFinite(points) || points < 0) {
    console.error("Prediction model returned malformed output:", output);
    throw new ModelOutputError("Prediction model returned an invalid result");
  }
  return points;
}

/**
 * Builds the prediction for one player. Throws NotFoundError for an
 * unknown player and InsufficientDataError if they have no games yet.
 */
async function getPlayerPrediction(playerId) {
  const player = await pool.query("SELECT id, full_name FROM players WHERE id = $1", [playerId]);
  if (player.rows.length === 0) {
    throw new NotFoundError("Player not found");
  }

  // Most recent first; rows without a points value can't be averaged.
  const { rows } = await pool.query(
    `SELECT pgs.points
     FROM player_game_stats pgs
     JOIN games g ON g.id = pgs.game_id
     WHERE pgs.player_id = $1 AND pgs.points IS NOT NULL
     ORDER BY g.game_date DESC`,
    [playerId]
  );
  if (rows.length === 0) {
    throw new InsufficientDataError("Not enough game history to make a prediction");
  }

  const points = rows.map((r) => r.points);
  const features = {
    recent_points_avg: average(points.slice(0, RECENT_WINDOW)),
    season_points_avg: average(points),
    games_used: points.length,
  };

  const predicted = runModel(features);

  return {
    player_id: player.rows[0].id,
    player_name: player.rows[0].full_name,
    predicted_points: round1(predicted),
    recent_points_avg: round1(features.recent_points_avg),
    season_points_avg: round1(features.season_points_avg),
    games_used: features.games_used,
    model_version: model.version,
  };
}

module.exports = { getPlayerPrediction, model };
