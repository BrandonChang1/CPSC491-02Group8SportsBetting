/** Experimental team-strength estimates from historical NBA player points. */
const { spawn } = require('node:child_process');
const path = require('node:path');
const pool = require('../db');

const root = path.resolve(__dirname, '../../..');
const python = process.env.PYTHON_COMMAND || (process.platform === 'win32' ? 'python' : 'python3');

async function fetchTeamPlayerHistories() {
  // players.team_id is nullable and is NOT filled by ingest_players(). Resolve
  // the player's last observed team from the games/matchup information instead.
  // When a genuine roster/team_id exists, prefer that over historical affiliation.
  // Do not restrict game dates to the current season: backfill includes 2024-25.
  const { rows } = await pool.query(`
    WITH historical AS (
      SELECT p.id AS player_id, p.team_id AS roster_team_id,
             g.game_date AS played_on, g.game_date::text AS game_date,
             pgs.points, pgs.minutes,
             COALESCE(t_at_game.id,
               CASE WHEN pgs.is_home IS TRUE THEN g.home_team_id
                    WHEN pgs.is_home IS FALSE THEN g.away_team_id END
             ) AS observed_team_id,
             ROW_NUMBER() OVER (
               PARTITION BY p.id ORDER BY g.game_date DESC, g.id DESC
             ) AS game_rank
      FROM player_game_stats pgs
      JOIN players p ON p.id = pgs.player_id
      JOIN games g ON g.id = pgs.game_id
      LEFT JOIN teams t_at_game
        ON t_at_game.abbreviation = split_part(BTRIM(pgs.matchup), ' ', 1)
       AND t_at_game.id IN (g.home_team_id, g.away_team_id)
      WHERE p.is_active = TRUE
        AND pgs.points IS NOT NULL
        AND g.game_date < CURRENT_DATE
    ), affiliations AS (
      SELECT player_id,
             COALESCE(MAX(roster_team_id),
                      MAX(observed_team_id) FILTER (WHERE game_rank = 1)) AS resolved_team_id,
             CASE WHEN MAX(roster_team_id) IS NOT NULL
                  THEN 'players.team_id' ELSE 'latest_historical_game' END AS roster_source
      FROM historical
      GROUP BY player_id
    ), eligible AS (
      SELECT a.resolved_team_id, a.roster_source, h.player_id,
             AVG(h.minutes) FILTER (WHERE h.game_rank <= 10) AS recent_minutes,
             MAX(h.played_on) AS latest_game
      FROM historical h
      JOIN affiliations a ON a.player_id = h.player_id
      WHERE h.game_rank <= 30 AND a.resolved_team_id IS NOT NULL
      GROUP BY a.resolved_team_id, a.roster_source, h.player_id
      HAVING COUNT(*) >= 3
    ), rotation AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY resolved_team_id
        ORDER BY recent_minutes DESC NULLS LAST, latest_game DESC, player_id
      ) AS player_rank
      FROM eligible
    )
    SELECT t.abbreviation AS tricode, h.player_id, h.game_date,
           h.points, h.minutes, r.roster_source,
           r.latest_game::text AS last_game_date
    FROM historical h
    JOIN rotation r ON r.player_id = h.player_id
    JOIN teams t ON t.id = r.resolved_team_id
    WHERE r.player_rank <= 15 AND h.game_rank <= 30
    ORDER BY t.abbreviation, h.player_id, h.played_on, h.game_date
  `);

  const teams = {};
  const players = new Map();
  for (const row of rows) {
    const tricode = String(row.tricode).toUpperCase();
    if (!teams[tricode]) teams[tricode] = [];
    const key = `${tricode}:${row.player_id}`;
    if (!players.has(key)) {
      const player = {
        games: [],
        rosterSource: row.roster_source,
        lastGameDate: row.last_game_date
      };
      teams[tricode].push(player);
      players.set(key, player);
    }
    players.get(key).games.push({
      game_date: row.game_date,
      points: row.points,
      minutes: row.minutes
    });
  }
  return teams;
}

function runTreeModel(teams) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [path.join(root, 'ml', 'predict_team_matchups.py')], { cwd: root });
    let stdout = '';
    let stderr = '';
    let settled = false;
    const timer = setTimeout(() => child.kill(), 40000);
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', error => { settled = true; clearTimeout(timer); reject(error); });
    child.on('close', code => {
      clearTimeout(timer);
      if (settled) return;
      if (code !== 0) return reject(new Error(stderr.trim() || 'Tree model execution failed'));
      try {
        const data = JSON.parse(stdout);
        if (!data.success) throw new Error(data.message || 'Tree model unavailable');
        resolve(new Map(Object.entries(data.teams || {})));
      } catch (error) { reject(error); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ teams }));
  });
}

function estimateMatchup(away, home) {
  if (!away || !home || !Number.isFinite(away.projectedPoints) || !Number.isFinite(home.projectedPoints)) {
    return null;
  }
  // A heuristic sigmoid, NOT a trained/calibrated NBA win classifier.
  const margin = home.projectedPoints - away.projectedPoints + 1.5;
  const homeFraction = Math.min(0.85, Math.max(0.15, 1 / (1 + Math.exp(-margin / 12))));
  const homeWinPercent = Math.round(homeFraction * 100);
  return {
    homeWinPercent,
    awayWinPercent: 100 - homeWinPercent,
    method: 'random_forest_player_points_heuristic',
    homeProjectedPoints: home.projectedPoints,
    awayProjectedPoints: away.projectedPoints,
    homePlayersUsed: home.playersUsed,
    awayPlayersUsed: away.playersUsed,
    homeLatestDataDate: home.latestGameDate,
    awayLatestDataDate: away.latestGameDate,
    homeHistoricalRosterPlayers: home.historicalRosterPlayers,
    awayHistoricalRosterPlayers: away.historicalRosterPlayers,
    modelVersion: 'random-forest-points-v1',
    coverage: home.playersUsed < 5 || away.playersUsed < 5 ? 'limited' : 'normal'
  };
}

async function fetchTreeTeamEstimates() {
  return runTreeModel(await fetchTeamPlayerHistories());
}

module.exports = { fetchTeamPlayerHistories, fetchTreeTeamEstimates, estimateMatchup };
