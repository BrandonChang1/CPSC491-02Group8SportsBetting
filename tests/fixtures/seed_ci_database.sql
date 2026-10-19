INSERT INTO teams (
    id,
    full_name,
    abbreviation,
    city
)
VALUES
    (
        900000001,
        'CI Home Team',
        'CIH',
        'Test City'
    ),
    (
        900000002,
        'CI Away Team',
        'CIA',
        'Test City'
    )
ON CONFLICT (id) DO NOTHING;


INSERT INTO players (
    id,
    full_name,
    first_name,
    last_name,
    is_active,
    team_id
)
VALUES (
    900000101,
    'CI Test Player',
    'CI',
    'Player',
    TRUE,
    900000001
)
ON CONFLICT (id) DO NOTHING;


INSERT INTO games (
    id,
    game_date,
    home_team_id,
    away_team_id
)
VALUES
    (
        'CI000001',
        '2025-01-01',
        900000001,
        900000002
    ),
    (
        'CI000002',
        '2025-01-03',
        900000002,
        900000001
    )
ON CONFLICT (id) DO NOTHING;


INSERT INTO player_game_stats (
    player_id,
    game_id,
    minutes,
    points,
    rebounds,
    assists,
    plus_minus,
    matchup,
    win_loss,
    field_goals_made,
    field_goals_attempted,
    field_goal_pct,
    three_pointers_made,
    three_pointers_attempted,
    three_point_pct,
    free_throws_made,
    free_throws_attempted,
    free_throw_pct,
    offensive_rebounds,
    defensive_rebounds,
    steals,
    blocks,
    turnovers,
    personal_fouls,
    opponent_team_id,
    is_home,
    recent_minutes_avg
)
VALUES
    (
        900000101,
        'CI000001',
        30,
        20,
        5,
        6,
        4,
        'CIH vs. CIA',
        'W',
        7,
        14,
        0.500,
        2,
        5,
        0.400,
        4,
        4,
        1.000,
        1,
        4,
        1,
        0,
        2,
        1,
        900000002,
        TRUE,
        NULL
    ),
    (
        900000101,
        'CI000002',
        34,
        24,
        6,
        7,
        2,
        'CIH @ CIA',
        'W',
        9,
        17,
        0.529,
        3,
        7,
        0.429,
        3,
        4,
        0.750,
        2,
        4,
        2,
        1,
        3,
        2,
        900000002,
        FALSE,
        30.0
    )
ON CONFLICT (player_id, game_id)
DO UPDATE SET
    minutes = EXCLUDED.minutes,
    points = EXCLUDED.points,
    rebounds = EXCLUDED.rebounds,
    assists = EXCLUDED.assists,
    plus_minus = EXCLUDED.plus_minus,
    matchup = EXCLUDED.matchup,
    win_loss = EXCLUDED.win_loss,
    field_goals_made = EXCLUDED.field_goals_made,
    field_goals_attempted = EXCLUDED.field_goals_attempted,
    field_goal_pct = EXCLUDED.field_goal_pct,
    three_pointers_made = EXCLUDED.three_pointers_made,
    three_pointers_attempted =
        EXCLUDED.three_pointers_attempted,
    three_point_pct = EXCLUDED.three_point_pct,
    free_throws_made = EXCLUDED.free_throws_made,
    free_throws_attempted =
        EXCLUDED.free_throws_attempted,
    free_throw_pct = EXCLUDED.free_throw_pct,
    offensive_rebounds =
        EXCLUDED.offensive_rebounds,
    defensive_rebounds =
        EXCLUDED.defensive_rebounds,
    steals = EXCLUDED.steals,
    blocks = EXCLUDED.blocks,
    turnovers = EXCLUDED.turnovers,
    personal_fouls = EXCLUDED.personal_fouls,
    opponent_team_id = EXCLUDED.opponent_team_id,
    is_home = EXCLUDED.is_home,
    recent_minutes_avg =
        EXCLUDED.recent_minutes_avg;