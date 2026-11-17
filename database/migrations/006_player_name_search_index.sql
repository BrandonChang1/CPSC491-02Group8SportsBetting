-- SCRUM-139: player search filters with full_name ILIKE '%term%' on every keystroke.
-- A B-tree can't serve a leading wildcard, so it scanned all players; a trigram
-- GIN index serves ILIKE substring matches of 3+ characters.
-- pg_trgm is a trusted extension (PostgreSQL 13+): the database owner can create it.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS players_full_name_trgm
    ON players USING gin (full_name gin_trgm_ops);
