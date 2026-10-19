const express = require("express");
const path = require("path");
const { spawn } = require("child_process");
const pool = require("../db");
const asyncHandler = require("../asyncHandler");
const { parseIntParam } = require("../validators");

const router = express.Router();
const python = process.env.PYTHON_COMMAND || (process.platform === "win32" ? "python" : "python3");
const root = path.join(__dirname, "../../..");

function executePython(scriptName, args = [], input) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [path.join(root, "ml", scriptName), ...args], { cwd: root });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timeout = setTimeout(() => child.kill(), 40000);
    child.stdout.on("data", data => { stdout += data; });
    child.stderr.on("data", data => { stderr += data; });
    child.on("error", error => { settled = true; clearTimeout(timeout); reject(error); });
    child.on("close", code => {
      clearTimeout(timeout);
      if (settled) return;
      if (code !== 0) return reject(new Error(stderr.trim() || "Python process failed"));
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error("Invalid Python JSON response")); }
    });
    if (input !== undefined) {
      child.stdin.on("error", () => {});
      child.stdin.end(JSON.stringify(input));
    } else {
      child.stdin.end();
    }
  });
}

router.get("/api/players/:id/prediction", asyncHandler(async (req, res) => {
  const id = parseIntParam(req.params.id, "player id");
  let games = [];
  let source = "database";
  let databaseError = null;

  try {
    const result = await pool.query(
      `SELECT g.game_date::text AS game_date, pgs.points, pgs.minutes
       FROM player_game_stats pgs
       JOIN games g ON g.id = pgs.game_id
       WHERE pgs.player_id = $1 AND pgs.points IS NOT NULL
       ORDER BY g.game_date ASC`,
      [id]
    );
    games = result.rows;
  } catch (error) {
    // A missing/unavailable DB also triggers the nba_api fallback.
    databaseError = error;
    console.warn("Prediction database lookup failed; using nba_api:", error.message);
  }

  if (!games.length) {
    source = "nba_api";
    let fetched;
    try {
      fetched = await executePython("fetch_nba_history.py", [String(id)]);
    } catch (error) {
      return res.status(503).json({ success: false, source, message: `NBA API unavailable: ${error.message}` });
    }
    if (!fetched.success || !fetched.games.length) {
      return res.status(503).json({
        success: false, source,
        message: fetched.message || "No player game history available from either source.",
      });
    }
    games = fetched.games;
  }

  const result = await executePython("predict_player.py", [], { games });
  return res.status(result.success ? 200 : 503).json({
    ...result,
    source,
    ...(databaseError ? { fallbackReason: "Database unavailable" } : {}),
  });
}));

module.exports = router;
