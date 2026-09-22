-- Migration 001: initial schema
-- Combines the team/player/game/stats tables from database/schema.sql
-- with the users table needed for Sprint 1 (auth comes later, in Sprint 4,
-- but the table is created now so the schema is stable early).
--
-- Written with IF NOT EXISTS so it's safe to re-run against a database
-- that was already created by hand from schema.sql.

CREATE TABLE IF NOT EXISTS teams (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    abbreviation VARCHAR(10) NOT NULL UNIQUE,
    city VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS players (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    is_active BOOLEAN NOT NULL,
    team_id BIGINT,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS games (
    id VARCHAR(20) PRIMARY KEY,
    game_date DATE NOT NULL,
    home_team_id BIGINT NOT NULL,
    away_team_id BIGINT NOT NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id),
    FOREIGN KEY (away_team_id) REFERENCES teams(id),
    CHECK (home_team_id <> away_team_id)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    player_id BIGINT NOT NULL,
    game_id VARCHAR(20) NOT NULL,
    minutes INTEGER,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    plus_minus INTEGER,
    matchup VARCHAR(50),
    win_loss VARCHAR(1) CHECK (win_loss IN ('W', 'L')),
    PRIMARY KEY (player_id, game_id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (game_id) REFERENCES games(id)
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
