-- Read-only diagnosis for upcoming-games player and team coverage.
-- Run against your LOCAL/DEVELOPMENT Postgres database with psql -f.
-- No inserts, updates or schema changes.

SELECT 'teams' AS metric, COUNT(*) AS total FROM teams
UNION ALL SELECT 'players', COUNT(*) FROM players
UNION ALL SELECT 'players with nonnull team_id', COUNT(*) FROM players WHERE team_id IS NOT NULL
UNION ALL SELECT 'active players with nonnull team_id', COUNT(*) FROM players WHERE is_active = TRUE AND team_id IS NOT NULL
UNION ALL SELECT 'games', COUNT(*) FROM games
UNION ALL SELECT 'player_game_stats', COUNT(*) FROM player_game_stats
UNION ALL SELECT 'stats with matchup', COUNT(*) FROM player_game_stats WHERE matchup IS NOT NULL
UNION ALL SELECT 'stats with points', COUNT(*) FROM player_game_stats WHERE points IS NOT NULL
UNION ALL SELECT 'stats with home-away flag', COUNT(*) FROM player_game_stats WHERE is_home IS NOT NULL;

SELECT MIN(game_date) AS first_game_date, MAX(game_date) AS last_game_date,
       COUNT(*) AS stored_games
FROM games;

-- Per-team coverage using actual played-game team affiliations, NOT the
-- nullable player.team_id. Check these rows against the upcoming schedule.
WITH game_affiliation AS (
  SELECT pgs.player_id, g.id AS game_id, g.game_date,
         COALESCE(t_at_game.id,
            CASE WHEN pgs.is_home IS TRUE THEN g.home_team_id
                 WHEN pgs.is_home IS FALSE THEN g.away_team_id END) AS team_id
  FROM player_game_stats pgs
  JOIN games g ON g.id = pgs.game_id
  LEFT JOIN teams t_at_game
    ON t_at_game.abbreviation = split_part(BTRIM(pgs.matchup), ' ', 1)
   AND t_at_game.id IN (g.home_team_id, g.away_team_id)
  WHERE pgs.points IS NOT NULL AND g.game_date < CURRENT_DATE
)
SELECT t.abbreviation,
       COUNT(DISTINCT ga.player_id) AS players_with_points_history,
       COUNT(DISTINCT ga.game_id) AS stored_team_games,
       MAX(ga.game_date) AS latest_stored_game
FROM teams t
LEFT JOIN game_affiliation ga ON ga.team_id = t.id
GROUP BY t.abbreviation
ORDER BY t.abbreviation;
