<<<<<<< Updated upstream
/** Transparent, non-ML team win estimates from recently completed games. */
=======
/** Historical team win-rate fallback; distinct games, not per-player wins. */
const pool = require('../db');
>>>>>>> Stashed changes

function estimateWinProbabilities(away, home) {
  if (!away || !home || away.games < 3 || home.games < 3) return null;
  const awayRate = (away.wins + 2.5) / (away.games + 5);
  const homeRate = (home.wins + 2.5) / (home.games + 5);
  const homeProbability = Math.max(0.1, Math.min(0.9, 0.53 + (homeRate - awayRate) * 0.7));
  const homePct = Math.round(homeProbability * 100);
  return {
    homeWinPercent: homePct,
    awayWinPercent: 100 - homePct,
    method: 'recent_results_baseline',
    homeGamesUsed: home.games,
    awayGamesUsed: away.games,
    homeSource: home.source || 'postgres',
    awaySource: away.source || 'postgres'
  };
}

async function fetchRecentTeamRecords() {
<<<<<<< Updated upstream
  const pool = require('../db');
  // Group by game/team to avoid counting every player's W/L as an individual game.
  // Current team membership is used for attribution; historical trades can affect results.
=======
  // A player's team_id may be NULL or reflect a later trade. Credit wins to
  // the team the player actually represented IN THAT GAME, via matchup.
  // is_home and the stored game's home/away IDs are the legacy-data fallback.
>>>>>>> Stashed changes
  const { rows } = await pool.query(`
    WITH attributed AS (
      SELECT g.id AS game_id, g.game_date,
             COALESCE(t_at_game.id,
               CASE WHEN pgs.is_home IS TRUE THEN g.home_team_id
                    WHEN pgs.is_home IS FALSE THEN g.away_team_id END
             ) AS team_id,
             pgs.win_loss
      FROM player_game_stats pgs
      JOIN games g ON g.id = pgs.game_id
      LEFT JOIN teams t_at_game
        ON t_at_game.abbreviation = split_part(BTRIM(pgs.matchup), ' ', 1)
       AND t_at_game.id IN (g.home_team_id, g.away_team_id)
      WHERE pgs.win_loss IN ('W', 'L') AND g.game_date < CURRENT_DATE
    ), team_games AS (
      SELECT team_id, game_id, game_date,
             MAX(CASE WHEN win_loss = 'W' THEN 1 ELSE 0 END) AS won
      FROM attributed
      WHERE team_id IS NOT NULL
      GROUP BY team_id, game_id, game_date
    ), ranked AS (
      SELECT team_id, won, ROW_NUMBER() OVER (
        PARTITION BY team_id ORDER BY game_date DESC, game_id DESC
      ) AS rn
      FROM team_games
    )
    SELECT t.abbreviation AS tricode, COUNT(*)::int AS games,
           COALESCE(SUM(r.won), 0)::int AS wins
    FROM ranked r JOIN teams t ON t.id = r.team_id
    WHERE r.rn <= 10
    GROUP BY t.abbreviation
  `);
  return new Map(rows.map(row => [
    String(row.tricode).toUpperCase(),
    { games: Number(row.games), wins: Number(row.wins) }
  ]));
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
