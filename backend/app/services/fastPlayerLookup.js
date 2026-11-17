/** Fast, database-backed responses for the existing player-search UI. */
const pool = require("../db");

function seasonForDate(dateValue) {
  const date = new Date(dateValue);
  const year = date.getUTCFullYear();
  const start = date.getUTCMonth() >= 9 ? year : year - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

async function searchPlayersInDatabase(term) {
  const { rows } = await pool.query(
    `SELECT id, full_name AS name, is_active
     FROM players
     WHERE full_name ILIKE $1
     ORDER BY is_active DESC,
       CASE WHEN full_name ILIKE $2 THEN 0 ELSE 1 END,
       full_name, id
     LIMIT 10`,
    [`%${term}%`, `${term}%`]
  );
  return rows;
}

async function getPlayerStatsFromDatabase(id, review) {
  const player = await pool.query(
    "SELECT id, full_name AS name, is_active FROM players WHERE id = $1",
    [id]
  );
  if (!player.rows.length) return null;

  // Fetch only the selected review size. The full-season option is limited to
  // the most recent season found in the local database, not all historical years.
  const { rows } = await pool.query(
    `SELECT g.game_date, pgs.matchup, pgs.win_loss, pgs.minutes,
            pgs.points, pgs.rebounds, pgs.assists, pgs.plus_minus
     FROM player_game_stats pgs
     JOIN games g ON g.id = pgs.game_id
     WHERE pgs.player_id = $1
     ORDER BY g.game_date DESC, g.id DESC
     LIMIT 100`,
    [id]
  );
  if (!rows.length) return null;
  const season = seasonForDate(rows[0].game_date);
  const seasonRows = rows.filter((row) => seasonForDate(row.game_date) === season);
  const chosen = review === "season" ? seasonRows : seasonRows.slice(0, Number(review));
  const fields = ["minutes", "points", "rebounds", "assists", "plus_minus"];
  const averages = {};
  for (const field of fields) {
    const numbers = chosen.map((row) => row[field] == null ? NaN : Number(row[field])).filter((value) => Number.isFinite(value));
    averages[field] = numbers.length
      ? Math.round((numbers.reduce((sum, value) => sum + value, 0) / numbers.length) * 10) / 10
      : null;
  }
  const data = chosen.map((row) => ({
    GAME_DATE: new Date(row.game_date).toISOString().slice(0, 10),
    MATCHUP: row.matchup,
    WL: row.win_loss,
    MIN: row.minutes,
    PTS: row.points,
    REB: row.rebounds,
    AST: row.assists,
    PLUS_MINUS: row.plus_minus
  }));
  const review_label = review === "season" ? "Season Review" : `Last ${review} Games`;
  return {
    success: true, player: player.rows[0], season, review, review_label,
    averages, data, source: "database",
    message: `Loaded ${review_label.toLowerCase()} from local database.`
  };
}

module.exports = { searchPlayersInDatabase, getPlayerStatsFromDatabase };
