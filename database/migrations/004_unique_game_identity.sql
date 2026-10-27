-- A source change must not create a second record for the same NBA game.
-- Existing duplicates require manual reconciliation; never delete historical stats.
CREATE UNIQUE INDEX IF NOT EXISTS games_date_teams_unique
    ON games (game_date, home_team_id, away_team_id);
