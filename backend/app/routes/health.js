const express = require("express");
const pool = require("../db");
const asyncHandler = require("../asyncHandler");
const { ValidationError } = require("../errors");

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

const DEFAULT_MAX_AGE_HOURS = 48;

// Same logic as FRESHNESS_QUERY in data/ingestion/incremental_refresh.py; keep the two in sync.
const FRESHNESS_QUERY = `
  WITH scoped AS (
    SELECT * FROM ingestion_refresh_runs
    WHERE ($1::bigint IS NULL OR player_id = $1::bigint)
      AND ($2::text IS NULL OR season = $2::text)
  ),
  latest AS (SELECT * FROM scoped ORDER BY id DESC LIMIT 1),
  success AS (
    SELECT MAX(finished_at) AS last_successful_refresh,
           MAX(finished_at) < CURRENT_TIMESTAMP - $3::float * INTERVAL '1 hour' AS too_old
    FROM scoped WHERE status = 'succeeded'
  )
  SELECT latest.status, latest.started_at, latest.finished_at, latest.error_type,
         success.last_successful_refresh,
         COALESCE(success.too_old, TRUE) AS is_stale,
         CASE WHEN latest.status IN ('failed', 'running') THEN latest.status
              WHEN success.last_successful_refresh IS NULL THEN 'never_refreshed'
              WHEN success.too_old THEN 'stale'
              ELSE 'fresh' END AS freshness
  FROM success LEFT JOIN latest ON TRUE`;

function maxAgeHours() {
  const hours = Number(process.env.DATA_FRESHNESS_MAX_AGE_HOURS ?? DEFAULT_MAX_AGE_HOURS);
  if (!Number.isFinite(hours) || hours <= 0) {
    throw new Error("DATA_FRESHNESS_MAX_AGE_HOURS must be a positive number of hours");
  }
  return hours;
}

function parseScope(query) {
  const { player_id: playerId, season } = query;
  if ((playerId === undefined) !== (season === undefined)) {
    throw new ValidationError("player_id and season must be given together");
  }
  if (playerId === undefined) return { playerId: null, season: null };
  const id = Number(playerId);
  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new ValidationError("player_id must be a positive integer");
  }
  if (typeof season !== "string" || !/^\d{4}-\d{2}$/.test(season)) {
    throw new ValidationError("season must look like YYYY-YY");
  }
  return { playerId: id, season };
}

/**
 * GET /health/freshness[?player_id=&season=]
 * SCRUM-137: read-only NBA data freshness from ingestion_refresh_runs, for the
 * whole database or one player/season. freshness is one of fresh, stale,
 * failed, running or never_refreshed; the threshold comes from
 * DATA_FRESHNESS_MAX_AGE_HOURS (default 48).
 */
router.get(
  "/health/freshness",
  asyncHandler(async (req, res) => {
    const { playerId, season } = parseScope(req.query);
    const hours = maxAgeHours();
    const { rows } = await pool.query(FRESHNESS_QUERY, [playerId, season, hours]);
    const row = rows[0];
    res.json({
      scope: playerId === null ? "database" : { player_id: playerId, season },
      freshness: row.freshness,
      is_stale: row.is_stale,
      max_age_hours: hours,
      last_successful_refresh: row.last_successful_refresh,
      latest_attempt: row.status === null ? null : {
        status: row.status,
        started_at: row.started_at,
        finished_at: row.finished_at,
        error_type: row.error_type,
      },
    });
  })
);

module.exports = router;
