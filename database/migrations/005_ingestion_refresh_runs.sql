CREATE TABLE IF NOT EXISTS ingestion_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL CHECK (player_id > 0),
    season VARCHAR(7) NOT NULL,
    source TEXT NOT NULL DEFAULT 'ESPN' CHECK (source = 'ESPN'),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed')),
    source_rows INTEGER NOT NULL DEFAULT 0 CHECK (source_rows >= 0),
    inserted_rows INTEGER NOT NULL DEFAULT 0 CHECK (inserted_rows >= 0),
    skipped_rows INTEGER NOT NULL DEFAULT 0 CHECK (skipped_rows >= 0),
    error_type TEXT,
    CHECK ((status = 'running' AND finished_at IS NULL)
        OR (status <> 'running' AND finished_at IS NOT NULL AND finished_at >= started_at)),
    CHECK (inserted_rows + skipped_rows <= source_rows)
);

CREATE INDEX IF NOT EXISTS ingestion_refresh_runs_scope
    ON ingestion_refresh_runs (player_id, season, id DESC);
