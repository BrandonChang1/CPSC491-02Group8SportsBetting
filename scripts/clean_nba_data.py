import pandas as pd

def clean_player_game_log(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize NBA player game-log data for project use.

    Keeps MVP-relevant fields, standardizes column names and types,
    removes duplicates, and drops rows missing required identifiers.
    """
    
    cleaned = df.copy()

    # Keep only fields useful to the MVP
    columns_to_keep = [
        "Player_ID",
        "Game_ID",
        "GAME_DATE",
        "MATCHUP",
        "WL",
        "MIN",
        "PTS",
        "REB",
        "AST",
        "PLUS_MINUS",
    ]

    cleaned = cleaned[columns_to_keep]

    # Standardize column names
    cleaned.columns = [
        "player_id",
        "game_id",
        "game_date",
        "matchup",
        "win_loss",
        "minutes",
        "points",
        "rebounds",
        "assists",
        "plus_minus",
    ]

    # Normalize date format
    cleaned["game_date"] = pd.to_datetime(
        cleaned["game_date"],
        errors="coerce"
    )

    # Convert numeric fields safely
    numeric_columns = [
        "minutes",
        "points",
        "rebounds",
        "assists",
        "plus_minus",
    ]

    for column in numeric_columns:
        cleaned[column] = pd.to_numeric(
            cleaned[column],
            errors="coerce"
        )

    # Remove exact duplicate rows
    cleaned = cleaned.drop_duplicates()

    # Remove rows missing required identifiers
    cleaned = cleaned.dropna(
        subset=["player_id", "game_id", "game_date"]
    )

    return cleaned
