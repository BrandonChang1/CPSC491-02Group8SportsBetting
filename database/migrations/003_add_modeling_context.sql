ALTER TABLE player_game_stats
    ADD COLUMN IF NOT EXISTS opponent_team_id BIGINT,
    ADD COLUMN IF NOT EXISTS is_home BOOLEAN,
    ADD COLUMN IF NOT EXISTS recent_minutes_avg DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'player_game_stats_opponent_team_fk'
    ) THEN
        ALTER TABLE player_game_stats
            ADD CONSTRAINT player_game_stats_opponent_team_fk
            FOREIGN KEY (opponent_team_id)
            REFERENCES teams(id);
    END IF;
END
$$;