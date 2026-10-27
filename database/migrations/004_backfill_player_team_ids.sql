-- Fill existing players.team_id from the latest matchup stored for each player.
-- Example: "GSW vs. LAL" / "GSW @ LAL" -> GSW team ID.
-- No new column is needed: it already exists in 001_initial_schema.sql.
-- This describes the latest *stored* team, not necessarily today's roster.
WITH latest_team AS (
    SELECT DISTINCT ON (s.player_id)
        s.player_id,
        t.id AS team_id
    FROM player_game_stats s
    JOIN games g ON g.id = s.game_id
    JOIN teams t ON t.abbreviation = split_part(trim(s.matchup), ' ', 1)
    WHERE s.matchup IS NOT NULL
      AND (s.matchup LIKE '% vs. %' OR s.matchup LIKE '% @ %')
    ORDER BY s.player_id, g.game_date DESC, s.game_id DESC
)
UPDATE players p
SET team_id = lt.team_id
FROM latest_team lt
WHERE p.id = lt.player_id
  AND p.team_id IS NULL;
