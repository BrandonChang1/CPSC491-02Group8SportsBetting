-- Database schema goes here.
CREATE TABLE teams (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    abbreviation VARCHAR(10) NOT NULL UNIQUE,
    city VARCHAR(100)
);

CREATE TABLE players (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    is_active BOOLEAN NOT NULL,
    team_id BIGINT,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE games (
    id VARCHAR(20) PRIMARY KEY,
    game_date DATE NOT NULL,
    home_team_id BIGINT NOT NULL,
    away_team_id BIGINT NOT NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id),
    FOREIGN KEY (away_team_id) REFERENCES teams(id),
    CHECK (home_team_id <> away_team_id)
);

CREATE TABLE player_game_stats (
    player_id BIGINT NOT NULL,
    game_id VARCHAR(20) NOT NULL,
    minutes INTEGER,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    plus_minus INTEGER,
    matchup VARCHAR(50),
    win_loss VARCHAR(1) CHECK (win_loss IN ('W', 'L')),
    field_goals_made INTEGER,
    field_goals_attempted INTEGER,
    field_goal_pct DOUBLE PRECISION,
    three_pointers_made INTEGER,
    three_pointers_attempted INTEGER,
    three_point_pct DOUBLE PRECISION,
    free_throws_made INTEGER,
    free_throws_attempted INTEGER,
    free_throw_pct DOUBLE PRECISION,
    offensive_rebounds INTEGER,
    defensive_rebounds INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    personal_fouls INTEGER,
    opponent_team_id BIGINT,
    is_home BOOLEAN,
    recent_minutes_avg DOUBLE PRECISION,
    PRIMARY KEY (player_id, game_id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (opponent_team_id) REFERENCES teams(id)
);