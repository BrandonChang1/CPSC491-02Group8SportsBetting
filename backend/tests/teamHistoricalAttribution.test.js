/**
 * Regression tests: ingested NBA players have NULL team_id, but matchup game
 * history still lets upcoming-games forecasts and recent-results fallback work.
 * Requires a migrated PostgreSQL test database, as in the project's CI job.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env') });
const pool = require('../app/db');
const { fetchTeamPlayerHistories } = require('../app/services/treeTeamPrediction');
const { fetchRecentTeamRecords } = require('../app/services/teamWinPrediction');

const TEAM_A = 9400001;
const TEAM_B = 9400002;
const PLAYER_A = 9400001;
const PLAYER_B = 9400002;
const GAME_IDS = ['9400001', '9400002', '9400003'];

test.before(async () => {
  await pool.query(`
    INSERT INTO teams (id, full_name, abbreviation, city)
    VALUES ($1, 'Historical Test A', 'HQA', 'Test'),
           ($2, 'Historical Test B', 'HQB', 'Test')
    ON CONFLICT (id) DO NOTHING
  `, [TEAM_A, TEAM_B]);
  await pool.query(`
    INSERT INTO players (id, full_name, is_active, team_id)
    VALUES ($1, 'Historic Test Player A', TRUE, NULL),
           ($2, 'Historic Test Player B', TRUE, NULL)
    ON CONFLICT (id) DO NOTHING
  `, [PLAYER_A, PLAYER_B]);
  for (let n = 0; n < GAME_IDS.length; n++) {
    await pool.query(`
      INSERT INTO games (id, game_date, home_team_id, away_team_id)
      VALUES ($1, $2, $3, $4)
      ON CONFLICT (id) DO NOTHING
    `, [GAME_IDS[n], `2024-12-0${n + 1}`, TEAM_A, TEAM_B]);
    await pool.query(`
      INSERT INTO player_game_stats
        (player_id, game_id, points, minutes, matchup, win_loss)
      VALUES ($1, $2, $3, 32, 'HQA vs. HQB', 'W'),
             ($4, $2, $5, 30, 'HQB @ HQA', 'L')
      ON CONFLICT (player_id, game_id) DO NOTHING
    `, [PLAYER_A, GAME_IDS[n], 20 + n, PLAYER_B, 17 + n]);
  }
});

test.after(async () => {
  await pool.query('DELETE FROM player_game_stats WHERE player_id IN ($1, $2)', [PLAYER_A, PLAYER_B]);
  await pool.query('DELETE FROM games WHERE id = ANY($1)', [GAME_IDS]);
  await pool.query('DELETE FROM players WHERE id IN ($1, $2)', [PLAYER_A, PLAYER_B]);
  await pool.query('DELETE FROM teams WHERE id IN ($1, $2)', [TEAM_A, TEAM_B]);
  await pool.end();
});

test('player histories are associated to teams even when players.team_id is NULL', async () => {
  const history = await fetchTeamPlayerHistories();
  const a = history.HQA.find(p => p.games.length === 3 && p.games[0].points === 20);
  const b = history.HQB.find(p => p.games.length === 3 && p.games[0].points === 17);
  assert.ok(a, 'home player should be found via stored matchup');
  assert.ok(b, 'away player should be found via stored matchup');
  assert.equal(a.rosterSource, 'latest_historical_game');
  assert.equal(b.rosterSource, 'latest_historical_game');
  assert.equal(a.lastGameDate, '2024-12-03');
});

test('team win fallback counts distinct games without players.team_id', async () => {
  const records = await fetchRecentTeamRecords();
  assert.deepEqual(records.get('HQA'), { games: 3, wins: 3 });
  assert.deepEqual(records.get('HQB'), { games: 3, wins: 0 });
});
