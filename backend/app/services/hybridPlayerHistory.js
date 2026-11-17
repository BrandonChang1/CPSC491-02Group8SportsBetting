/** Shared per-process history cache; expanding 5 -> 10 fetches only missing dates. */
const { execFile } = require("node:child_process");
const path = require("node:path");
const { promisify } = require("node:util");
const { getPlayerStatsFromDatabase } = require("./fastPlayerLookup");
const execFileAsync = promisify(execFile);
const cache = new Map();
const CHECK_TTL_MS = 5 * 60 * 1000;
const MAX_PLAYERS = 100;
const REPO_ROOT = path.resolve(__dirname, "../../..");
const script = path.join(REPO_ROOT, "scripts", "fetch_missing_player_games.py");
const python = process.env.PYTHON_COMMAND || (process.platform === "win32" ? "python" : "python3");

function seasonNow(date = new Date()) {
  const year = date.getUTCFullYear();
  const start = date.getUTCMonth() >= 9 ? year : year - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}
function finiteMean(rows, key) {
  const values = rows.map(row => Number(row[key])).filter((v, i) => rowPresent(rows[i][key]) && Number.isFinite(v));
  return values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length * 10) / 10 : null;
}
function rowPresent(value) { return value !== null && value !== undefined && value !== ""; }
function merge(rows, newer) {
  const byDate = new Map(rows.map(row => [row.GAME_DATE, row]));
  for (const row of newer) if (row && /^\d{4}-\d{2}-\d{2}$/.test(row.GAME_DATE)) byDate.set(row.GAME_DATE, row);
  return [...byDate.values()].sort((a, b) => b.GAME_DATE.localeCompare(a.GAME_DATE));
}
async function missingFromEspn(id, season, limit, knownDates, newerThan = "") {
  const { stdout } = await execFileAsync(python, [script, String(id), season, String(limit), JSON.stringify(knownDates), newerThan], {
    timeout: 45000, maxBuffer: 1024 * 1024
  });
  const result = JSON.parse(stdout);
  if (!result.success) throw new Error(result.message || "ESPN unavailable");
  return result.data;
}
async function retrieve(id, review, displayName = "") {
  const season = seasonNow();
  const key = `${id}:${season}`;
  let entry = cache.get(key);
  if (!entry) {
    const local = await getPlayerStatsFromDatabase(id, "season").catch(() => null);
    // The previous DB lookup chooses its own latest season. Do not mix seasons.
    const localRows = local && local.season === season ? local.data : [];
    entry = { rows: localRows, player: local?.player || null, checkedAt: 0, complete: false, pending: null, source: localRows.length ? "database" : "espn" };
    cache.set(key, entry);
    if (cache.size > MAX_PLAYERS) cache.delete(cache.keys().next().value);
  }
  const needed = review === "season" ? 100 : Number(review);
  // A stale 5-game cache is checked again after TTL, even if it is "full".
  const shouldCheck = Date.now() - entry.checkedAt > CHECK_TTL_MS || (!entry.complete && entry.rows.length < needed);
  if (shouldCheck && !entry.pending) {
    entry.pending = (async () => {
      try {
        // Request only slots that are not already cached, plus a small freshness
        // window if an old 5-game cache may have missed newly played games.
        const deficit = Math.max(0, needed - entry.rows.length);
        const fetchCount = deficit || 2;
        const newestDate = deficit === 0 && entry.rows.length ? entry.rows[0].GAME_DATE : "";
        const missing = await missingFromEspn(id, season, fetchCount, entry.rows.map(row => row.GAME_DATE), newestDate);
        entry.rows = merge(entry.rows, missing);
        entry.warning = null;
        if (missing.length) entry.source = entry.source === "database" ? "database+espn" : "espn";
        entry.complete = !newestDate && missing.length < fetchCount;
        entry.checkedAt = Date.now();
      } catch (error) {
        entry.checkedAt = Date.now(); // prevent repeated expensive failures
        if (!entry.rows.length) throw error;
        entry.warning = `ESPN refresh unavailable; showing cached games: ${error.message}`;
      }
    })().finally(() => { entry.pending = null; });
  }
  if (entry.pending) await entry.pending;
  const chosen = entry.rows.slice(0, needed);
  const reviews = { "5": "Last 5 Games", "10": "Last 10 Games", season: "Season Review" };
  const review_label = review === "season" ? "Season Review" : reviews[review];
  return {
    success: true, player: entry.player || { id: Number(id), name: displayName || `Player ${id}` },
    season, review, review_label, data: chosen,
    averages: Object.fromEntries([["MIN", "minutes"], ["PTS", "points"], ["REB", "rebounds"], ["AST", "assists"], ["PLUS_MINUS", "plus_minus"]].map(([column, name]) => [name, finiteMean(chosen, column)])),
    source: entry.source, cached_games: entry.rows.length, warning: entry.warning || null,
    message: `Loaded ${chosen.length} games from ${entry.source}.`
  };
}
module.exports = { retrieve, seasonNow, merge, cache };
