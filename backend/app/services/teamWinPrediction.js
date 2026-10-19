/** Transparent, non-ML team win estimates from recently completed games. */
const pool = require('../db');

function estimateWinProbabilities(away, home) {
  if (!away || !home || away.games < 3 || home.games < 3) return null;
  // Smoothed recent win rates (5 prior games at 50%) prevent extreme estimates.
  const awayRate = (away.wins + 2.5) / (away.games + 5);
  const homeRate = (home.wins + 2.5) / (home.games + 5);
  // Two equally matched teams: home 53%, away 47%.
  const homeProbability = Math.max(0.1, Math.min(0.9, 0.53 + (homeRate - awayRate) * 0.7));
  const homePct = Math.round(homeProbability * 100);
  return {
    homeWinPercent: homePct,
    awayWinPercent: 100 - homePct,
    method: 'recent_results_baseline',
    homeGamesUsed: home.games,
    awayGamesUsed: away.games
  };
}

async function fetchRecentTeamRecords() {
  // Group by game/team to avoid counting every player's W/L as an individual game.
  // Current team membership is used for attribution; historical trades can affect results.
  const { rows } = await pool.query(`
    WITH team_games AS (
      SELECT p.team_id, g.id AS game_id, g.game_date,
             MAX(CASE WHEN pgs.win_loss = 'W' THEN 1 ELSE 0 END) AS won
      FROM player_game_stats pgs
      JOIN players p ON p.id = pgs.player_id
      JOIN games g ON g.id = pgs.game_id
      WHERE p.team_id IN (g.home_team_id, g.away_team_id)
        AND pgs.win_loss IN ('W', 'L')
        AND g.game_date < CURRENT_DATE
      GROUP BY p.team_id, g.id, g.game_date
    ), ranked AS (
      SELECT team_id, won, ROW_NUMBER() OVER
        (PARTITION BY team_id ORDER BY game_date DESC, game_id DESC) AS rn
      FROM team_games
    )
    SELECT t.abbreviation AS tricode, COUNT(*)::int AS games,
           COALESCE(SUM(r.won), 0)::int AS wins
    FROM ranked r JOIN teams t ON t.id = r.team_id
    WHERE rn <= 10 GROUP BY t.abbreviation
  `);
  return new Map(rows.map(row => [row.tricode.toUpperCase(), { games: Number(row.games), wins: Number(row.wins) }]));
}

function addPredictions(games, records) {
  return games.map(game => ({
    ...game,
    winPrediction: estimateWinProbabilities(
      records.get(String(game.awayTeam?.tricode || '').toUpperCase()),
      records.get(String(game.homeTeam?.tricode || '').toUpperCase())
    )
  }));
}

module.exports = { estimateWinProbabilities, fetchRecentTeamRecords, addPredictions };
