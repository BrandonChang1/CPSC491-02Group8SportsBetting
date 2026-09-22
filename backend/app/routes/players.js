const express = require("express");
const pool = require("../db");

const router = express.Router();

/**
 * GET /players?skip=0&limit=50
 * Basic player listing (US-1/US-3). Full search-by-name comes in Sprint 2 —
 * this just proves the frontend -> API -> DB path works end to end.
 */
router.get("/players", async (req, res) => {
  const skip = parseInt(req.query.skip, 10) || 0;
  const limit = parseInt(req.query.limit, 10) || 50;

  if (limit > 200) {
    return res.status(400).json({ error: "limit cannot exceed 200" });
  }

  try {
    const { rows } = await pool.query(
      `SELECT id, full_name, first_name, last_name, is_active, team_id
       FROM players
       ORDER BY id
       OFFSET $1 LIMIT $2`,
      [skip, limit]
    );
    res.json(rows);
  } catch (err) {
    console.error("GET /players error:", err.message);
    res.status(500).json({ error: "Failed to fetch players" });
  }
});

/**
 * GET /players/:id
 * Single player lookup by id.
 */
router.get("/players/:id", async (req, res) => {
  const { id } = req.params;

  try {
    const { rows } = await pool.query(
      `SELECT id, full_name, first_name, last_name, is_active, team_id
       FROM players
       WHERE id = $1`,
      [id]
    );

    if (rows.length === 0) {
      return res.status(404).json({ error: "Player not found" });
    }

    res.json(rows[0]);
  } catch (err) {
    console.error("GET /players/:id error:", err.message);
    res.status(500).json({ error: "Failed to fetch player" });
  }
});

module.exports = router;
