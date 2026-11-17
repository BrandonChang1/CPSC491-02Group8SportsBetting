-- M02 read-only stored export: Stephen Curry (player_id 201939),
-- one preserved 2024-25 game and one refreshed 2025-26 game.
SELECT pgs.player_id, pgs.game_id, g.game_date, pgs.is_home, t.abbreviation AS opponent,
       pgs.opponent_team_id, pgs.minutes, pgs.points,
       pgs.field_goals_made, pgs.field_goals_attempted, pgs.field_goal_pct,
       pgs.three_pointers_made, pgs.three_pointers_attempted, pgs.three_point_pct,
       pgs.free_throws_made, pgs.free_throws_attempted, pgs.free_throw_pct
FROM player_game_stats pgs
JOIN games g ON g.id = pgs.game_id
JOIN teams t ON t.id = pgs.opponent_team_id
WHERE pgs.player_id = 201939 AND g.game_date IN ('2025-04-13', '2025-10-21')
ORDER BY g.game_date
