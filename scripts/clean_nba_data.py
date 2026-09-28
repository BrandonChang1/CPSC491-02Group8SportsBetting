import pandas as pd


def clean_player_game_log(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize NBA player game-log data for project use.

    Keeps MVP and ML-relevant fields, standardizes column names and types,
    removes duplicates, and drops rows missing required identifiers.
    """

    cleaned = df.copy()

    columns_to_keep = [
        "Player_ID",
        "Game_ID",
        "GAME_DATE",
        "MATCHUP",
        "WL",
        "MIN",
        "FGM",
        "FGA",
        "FG_PCT",
        "FG3M",
        "FG3A",
        "FG3_PCT",
        "FTM",
        "FTA",
        "FT_PCT",
        "OREB",
        "DREB",
        "REB",
        "AST",
        "STL",
        "BLK",
        "TOV",
        "PF",
        "PTS",
        "PLUS_MINUS",
    ]

    cleaned = cleaned[columns_to_keep]

    cleaned.columns = [
        "player_id",
        "game_id",
        "game_date",
        "matchup",
        "win_loss",
        "minutes",
        "field_goals_made",
        "field_goals_attempted",
        "field_goal_pct",
        "three_pointers_made",
        "three_pointers_attempted",
        "three_point_pct",
        "free_throws_made",
        "free_throws_attempted",
        "free_throw_pct",
        "offensive_rebounds",
        "defensive_rebounds",
        "rebounds",
        "assists",
        "steals",
        "blocks",
        "turnovers",
        "personal_fouls",
        "points",
        "plus_minus",
    ]

    cleaned["game_date"] = pd.to_datetime(
        cleaned["game_date"],
        errors="coerce",
    )

    numeric_columns = [
        "minutes",
        "field_goals_made",
        "field_goals_attempted",
        "field_goal_pct",
        "three_pointers_made",
        "three_pointers_attempted",
        "three_point_pct",
        "free_throws_made",
        "free_throws_attempted",
        "free_throw_pct",
        "offensive_rebounds",
        "defensive_rebounds",
        "rebounds",
        "assists",
        "steals",
        "blocks",
        "turnovers",
        "personal_fouls",
        "points",
        "plus_minus",
    ]

    for column in numeric_columns:
        cleaned[column] = pd.to_numeric(
            cleaned[column],
            errors="coerce",
        )

    cleaned = cleaned.drop_duplicates()

    cleaned = cleaned.dropna(
        subset=["player_id", "game_id", "game_date"]
    )

    return cleaned