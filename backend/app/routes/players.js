const express = require("express");
const pool = require("../db");
const asyncHandler = require("../asyncHandler");
const { parsePagination, parseIntParam } = require("../validators");
const { NotFoundError } = require("../errors");
const { getPlayerPrediction } = require("../services/prediction");
const { requireAuth } = require("./auth");
const router = express.Router();

/**
 * GET /players?search=&skip=&limit=
 *
 * Lists players, optionally filtered by a partial, case-insensitive name
 * match (US-4 — "search for an NBA player by name"). Without ?search=
 * this behaves like the plain Sprint 1 listing. Pagination (skip/limit)
 * and its validation apply either way.
 */
router.get(
  "/players",
  asyncHandler(async (req, res) => {
    const { skip, limit } = parsePagination(req.query);
    const search = typeof req.query.search === "string" ? req.query.search.trim() : "";

    const { rows } = search
      ? await pool.query(
          `SELECT id, full_name, first_name, last_name, is_active, team_id
           FROM players
           WHERE full_name ILIKE $1
           ORDER BY full_name
           OFFSET $2 LIMIT $3`,
          [`%${search}%`, skip, limit]
        )
      : await pool.query(
          `SELECT id, full_name, first_name, last_name, is_active, team_id
           FROM players
           ORDER BY id
           OFFSET $1 LIMIT $2`,
          [skip, limit]
        );

    res.json(rows);
  })
);

/**
 * GET /players/:id
 *
 * Player details (US-4 continued — "selecting a result opens the player
 * page"). Joins the player's team so the frontend gets team name/
 * abbreviation in one call instead of a second round trip.
 */
router.get(
  "/players/:id",
  asyncHandler(async (req, res) => {
    const id = parseIntParam(req.params.id, "player id");

    const { rows } = await pool.query(
      `SELECT p.id, p.full_name, p.first_name, p.last_name, p.is_active, p.team_id,
              t.full_name AS team_name, t.abbreviation AS team_abbreviation
       FROM players p
       LEFT JOIN teams t ON t.id = p.team_id
       WHERE p.id = $1`,
      [id]
    );

    if (rows.length === 0) {
      throw new NotFoundError("Player not found");
    }

    res.json(rows[0]);
  })
);

/**
 * GET /players/:id/games?skip=&limit=
 *
 * Player game history (US-5 — "view recent player performances"). Returns
 * the player's game log, most recent first, joined against `games` for
 * the date. 404s if the player id itself doesn't exist, rather than
 * silently returning an empty history for a typo'd id.
 */
router.get(
  "/players/:id/games",
  asyncHandler(async (req, res) => {
    const id = parseIntParam(req.params.id, "player id");
    // Defaults tuned for a season-length view (82 games) rather than the
    // generic 50/200 used for player listings.
    const { skip, limit } = parsePagination(req.query, { defaultLimit: 10, maxLimit: 82 });

    const playerExists = await pool.query("SELECT 1 FROM players WHERE id = $1", [id]);
    if (playerExists.rows.length === 0) {
      throw new NotFoundError("Player not found");
    }

    const { rows } = await pool.query(
      `SELECT g.id AS game_id, g.game_date, pgs.matchup, pgs.win_loss,
              pgs.minutes, pgs.points, pgs.rebounds, pgs.assists, pgs.plus_minus
       FROM player_game_stats pgs
       JOIN games g ON g.id = pgs.game_id
       WHERE pgs.player_id = $1
       ORDER BY g.game_date DESC
       OFFSET $2 LIMIT $3`,
      [id, skip, limit]
    );

    res.json(rows);
  })
);

/**
 * GET /players/:id/prediction
 *
 * Next-game points prediction (Sprint 3): predicted points, the player's
 * recent (last-5) and overall averages, and the model version used.
 * 404 for an unknown player, 422 if they have no games to predict from,
 * 503/502 if the model is unavailable or returns an unusable result.
 */
router.get(
  "/players/:id/prediction",
  requireAuth,
  asyncHandler(async (req, res) => {
    const id = parseIntParam(req.params.id, "player id");
    res.json(await getPlayerPrediction(id));
  })
);

/**
 * GET /players/:id/trends?limit=
 *
 * Recent scoring trend for a player (SCRUM-72). Looks at the player's most
 * recent `limit` games (default 10, max 50), compares the average of the last
 * 5 against the 5 games before them, and reports whether scoring is trending
 * up, down, or flat (a change of more than 1 point either way).
 *
 * Requires a login session, like the prediction route (SEC-02).
 *
 * - unknown player            -> 404
 * - non-numeric id / bad limit -> 400
 * - player with no games       -> 200 with games_analyzed 0 and null averages
 *   (the player exists, there is just nothing to trend yet)
 *
 * PASTE THIS INTO backend/app/routes/players.js, after the prediction route
 * and above `module.exports`. It uses only imports that file already has
 * (pool, asyncHandler, parsePagination, parseIntParam, NotFoundError,
 * requireAuth).
 */
router.get(
  "/players/:id/trends",
  requireAuth,
  asyncHandler(async (req, res) => {
    const id = parseIntParam(req.params.id, "player id");
    const { limit } = parsePagination(req.query, { defaultLimit: 10, maxLimit: 50 });

    const player = await pool.query("SELECT id FROM players WHERE id = $1", [id]);
    if (player.rows.length === 0) {
      throw new NotFoundError("Player not found");
    }

    const { rows } = await pool.query(
      `SELECT g.game_date::text AS game_date, pgs.points
       FROM player_game_stats pgs
       JOIN games g ON g.id = pgs.game_id
       WHERE pgs.player_id = $1 AND pgs.points IS NOT NULL
       ORDER BY g.game_date DESC
       LIMIT $2`,
      [id, limit]
    );

    // Newest-first from the query; flip to oldest-first so it reads as a trend.
    const games = rows.reverse().map((r) => ({ game_date: r.game_date, points: Number(r.points) }));

    const average = (list) =>
      list.length === 0 ? null : Math.round((list.reduce((sum, g) => sum + g.points, 0) / list.length) * 10) / 10;

    const recent = games.slice(-5);
    const previous = games.slice(-10, -5);
    const recentAverage = average(recent);
    const previousAverage = average(previous);

    let change = null;
    let direction = null;
    if (recentAverage !== null && previousAverage !== null) {
      change = Math.round((recentAverage - previousAverage) * 10) / 10;
      direction = change > 1 ? "up" : change < -1 ? "down" : "flat";
    }

    res.json({
      player_id: id,
      games_analyzed: games.length,
      recent_average: recentAverage,
      previous_average: previousAverage,
      change,
      direction,
      games,
    });
  })
);

module.exports = router;
