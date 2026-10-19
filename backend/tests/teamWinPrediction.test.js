const { test } = require('node:test');
const assert = require('node:assert/strict');
const { estimateWinProbabilities, addPredictions } = require('../app/services/teamWinPrediction');

test('equal records give small home-court advantage', () => {
  assert.deepEqual(estimateWinProbabilities({ games: 10, wins: 5 }, { games: 10, wins: 5 }), {
<<<<<<< Updated upstream
    homeWinPercent: 53, awayWinPercent: 47, method: 'recent_results_baseline', homeGamesUsed: 10, awayGamesUsed: 10
=======
    homeWinPercent: 53, awayWinPercent: 47, method: 'recent_results_baseline', homeGamesUsed: 10, awayGamesUsed: 10, homeSource: 'postgres', awaySource: 'postgres'
>>>>>>> Stashed changes
  });
});
test('better road team receives higher probability', () => {
  const p = estimateWinProbabilities({ games: 10, wins: 9 }, { games: 10, wins: 1 });
  assert.ok(p.awayWinPercent > p.homeWinPercent);
  assert.equal(p.homeWinPercent + p.awayWinPercent, 100);
});
test('insufficient or missing records returns no estimate', () => {
  assert.equal(estimateWinProbabilities(undefined, { games: 10, wins: 5 }), null);
  assert.equal(estimateWinProbabilities({ games: 2, wins: 2 }, { games: 10, wins: 5 }), null);
});
test('matches team abbreviations from the NBA schedule', () => {
  const games = [{ gameId: '1', homeTeam: { tricode: 'BOS' }, awayTeam: { tricode: 'NYK' } }];
  const enriched = addPredictions(games, new Map([['BOS', { games: 8, wins: 5 }], ['NYK', { games: 8, wins: 4 }]]));
  assert.equal(enriched[0].winPrediction.homeWinPercent + enriched[0].winPrediction.awayWinPercent, 100);
});
