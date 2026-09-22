const express = require("express");
const pool = require("../db");

const router = express.Router();

/**
 * GET /health
 * Sprint 1's core acceptance criterion: prove the API can reach Postgres.
 * Runs a trivial query (SELECT 1) — if the DB connection is broken, this
 * catches it and reports "database: disconnected" instead of crashing
 * or hanging.
 */
router.get("/health", async (req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok", database: "connected" });
  } catch (err) {
    console.error("Health check DB error:", err.message);
    res.status(503).json({ status: "ok", database: "disconnected" });
  }
});

module.exports = router;
