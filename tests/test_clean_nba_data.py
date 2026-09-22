import pandas as pd

from scripts.clean_nba_data import clean_player_game_log


def test_clean_player_game_log_basic():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123],
            "Game_ID": ["001"],
            "GAME_DATE": ["2026-01-15"],
            "MATCHUP": ["LAL vs. BOS"],
            "WL": ["W"],
            "MIN": ["35"],
            "PTS": ["28"],
            "REB": ["7"],
            "AST": ["9"],
            "PLUS_MINUS": ["12"],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert list(cleaned.columns) == [
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

    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["points"] == 28
    assert cleaned.iloc[0]["rebounds"] == 7
    assert cleaned.iloc[0]["assists"] == 9

def test_clean_player_game_log_removes_duplicates():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123, 123],
            "Game_ID": ["001", "001"],
            "GAME_DATE": ["2026-01-15", "2026-01-15"],
            "MATCHUP": ["LAL vs. BOS", "LAL vs. BOS"],
            "WL": ["W", "W"],
            "MIN": [35, 35],
            "PTS": [28, 28],
            "REB": [7, 7],
            "AST": [9, 9],
            "PLUS_MINUS": [12, 12],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1

def test_clean_player_game_log_drops_missing_required_fields():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123, 456],
            "Game_ID": ["001", None],
            "GAME_DATE": ["2026-01-15", "2026-01-16"],
            "MATCHUP": ["LAL vs. BOS", "NYK vs. MIA"],
            "WL": ["W", "L"],
            "MIN": [35, 30],
            "PTS": [28, 20],
            "REB": [7, 5],
            "AST": [9, 4],
            "PLUS_MINUS": [12, -3],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["game_id"] == "001"

def test_clean_player_game_log_converts_numeric_fields():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123],
            "Game_ID": ["001"],
            "GAME_DATE": ["2026-01-15"],
            "MATCHUP": ["LAL vs. BOS"],
            "WL": ["W"],
            "MIN": ["35"],
            "PTS": ["28"],
            "REB": ["7"],
            "AST": ["9"],
            "PLUS_MINUS": ["12"],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert cleaned["minutes"].dtype.kind in "fi"
    assert cleaned["points"].dtype.kind in "fi"
    assert cleaned["rebounds"].dtype.kind in "fi"
    assert cleaned["assists"].dtype.kind in "fi"
    assert cleaned["plus_minus"].dtype.kind in "fi"

def test_clean_player_game_log_drops_invalid_date():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123],
            "Game_ID": ["001"],
            "GAME_DATE": ["not-a-date"],
            "MATCHUP": ["LAL vs. BOS"],
            "WL": ["W"],
            "MIN": [35],
            "PTS": [28],
            "REB": [7],
            "AST": [9],
            "PLUS_MINUS": [12],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert cleaned.empty

def test_clean_player_game_log_handles_invalid_numeric_value():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123],
            "Game_ID": ["001"],
            "GAME_DATE": ["2026-01-15"],
            "MATCHUP": ["LAL vs. BOS"],
            "WL": ["W"],
            "MIN": ["35"],
            "PTS": ["not-a-number"],
            "REB": ["7"],
            "AST": ["9"],
            "PLUS_MINUS": ["12"],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert pd.isna(cleaned.iloc[0]["points"])

def test_clean_player_game_log_preserves_unique_games():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123, 123],
            "Game_ID": ["001", "002"],
            "GAME_DATE": ["2026-01-15", "2026-01-17"],
            "MATCHUP": ["LAL vs. BOS", "LAL @ NYK"],
            "WL": ["W", "L"],
            "MIN": [35, 33],
            "PTS": [28, 24],
            "REB": [7, 6],
            "AST": [9, 8],
            "PLUS_MINUS": [12, -4],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 2
    assert set(cleaned["game_id"]) == {"001", "002"}    

def test_clean_player_game_log_drops_missing_player_id():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123, None],
            "Game_ID": ["001", "002"],
            "GAME_DATE": ["2026-01-15", "2026-01-17"],
            "MATCHUP": ["LAL vs. BOS", "LAL @ NYK"],
            "WL": ["W", "L"],
            "MIN": [35, 33],
            "PTS": [28, 24],
            "REB": [7, 6],
            "AST": [9, 8],
            "PLUS_MINUS": [12, -4],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["game_id"] == "001"

def test_clean_player_game_log_handles_mixed_validity_rows():
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123, None, 456],
            "Game_ID": ["001", "002", None],
            "GAME_DATE": ["2026-01-15", "2026-01-16", "2026-01-17"],
            "MATCHUP": ["LAL vs. BOS", "NYK vs. MIA", "GSW vs. PHX"],
            "WL": ["W", "L", "W"],
            "MIN": [35, 30, 32],
            "PTS": [28, 20, 24],
            "REB": [7, 5, 6],
            "AST": [9, 4, 8],
            "PLUS_MINUS": [12, -3, 5],
        }
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["game_id"] == "001"    