const express = require("express");
const pool = require("../db");
const asyncHandler = require("../asyncHandler");
const { parsePagination, parseIntParam } = require("../validators");
const { NotFoundError } = require("../errors");

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

module.exports = router;
