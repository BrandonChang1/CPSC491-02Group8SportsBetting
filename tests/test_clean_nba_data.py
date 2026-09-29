import pandas as pd

from scripts.clean_nba_data import clean_player_game_log


def make_game_row(**overrides):
    row = {
        "Player_ID": 123,
        "Game_ID": "001",
        "GAME_DATE": "2026-01-15",
        "MATCHUP": "LAL vs. BOS",
        "WL": "W",
        "MIN": "35",
        "FGM": "10",
        "FGA": "20",
        "FG_PCT": "0.500",
        "FG3M": "4",
        "FG3A": "9",
        "FG3_PCT": "0.444",
        "FTM": "4",
        "FTA": "5",
        "FT_PCT": "0.800",
        "OREB": "1",
        "DREB": "6",
        "REB": "7",
        "AST": "9",
        "STL": "2",
        "BLK": "1",
        "TOV": "3",
        "PF": "2",
        "PTS": "28",
        "PLUS_MINUS": "12",
    }

    row.update(overrides)
    return row


def test_clean_player_game_log_basic():
    raw_df = pd.DataFrame([make_game_row()])

    cleaned = clean_player_game_log(raw_df)

    assert list(cleaned.columns) == [
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

    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["points"] == 28
    assert cleaned.iloc[0]["rebounds"] == 7
    assert cleaned.iloc[0]["assists"] == 9

    assert cleaned.iloc[0]["field_goals_made"] == 10
    assert cleaned.iloc[0]["field_goals_attempted"] == 20
    assert cleaned.iloc[0]["three_pointers_made"] == 4
    assert cleaned.iloc[0]["free_throws_attempted"] == 5

    assert cleaned.iloc[0]["offensive_rebounds"] == 1
    assert cleaned.iloc[0]["defensive_rebounds"] == 6
    assert cleaned.iloc[0]["steals"] == 2
    assert cleaned.iloc[0]["blocks"] == 1
    assert cleaned.iloc[0]["turnovers"] == 3
    assert cleaned.iloc[0]["personal_fouls"] == 2


def test_clean_player_game_log_removes_duplicates():
    game = make_game_row()

    raw_df = pd.DataFrame(
        [
            game,
            game.copy(),
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1


def test_clean_player_game_log_drops_missing_required_fields():
    raw_df = pd.DataFrame(
        [
            make_game_row(),
            make_game_row(
                Player_ID=456,
                Game_ID=None,
                GAME_DATE="2026-01-16",
                MATCHUP="NYK vs. MIA",
            ),
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["game_id"] == "001"


def test_clean_player_game_log_converts_numeric_fields():
    raw_df = pd.DataFrame([make_game_row()])

    cleaned = clean_player_game_log(raw_df)

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
        assert cleaned[column].dtype.kind in "fi"


def test_clean_player_game_log_drops_invalid_date():
    raw_df = pd.DataFrame(
        [
            make_game_row(
                GAME_DATE="not-a-date",
            )
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert cleaned.empty


def test_clean_player_game_log_handles_invalid_numeric_value():
    raw_df = pd.DataFrame(
        [
            make_game_row(
                PTS="not-a-number",
            )
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert pd.isna(cleaned.iloc[0]["points"])


def test_clean_player_game_log_preserves_unique_games():
    raw_df = pd.DataFrame(
        [
            make_game_row(),
            make_game_row(
                Game_ID="002",
                GAME_DATE="2026-01-17",
                MATCHUP="LAL @ NYK",
                WL="L",
                MIN="33",
                PTS="24",
                PLUS_MINUS="-4",
            ),
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 2
    assert set(cleaned["game_id"]) == {"001", "002"}


def test_clean_player_game_log_drops_missing_player_id():
    raw_df = pd.DataFrame(
        [
            make_game_row(),
            make_game_row(
                Player_ID=None,
                Game_ID="002",
                GAME_DATE="2026-01-17",
                MATCHUP="LAL @ NYK",
            ),
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["game_id"] == "001"


def test_clean_player_game_log_handles_mixed_validity_rows():
    raw_df = pd.DataFrame(
        [
            make_game_row(),
            make_game_row(
                Player_ID=None,
                Game_ID="002",
                GAME_DATE="2026-01-16",
                MATCHUP="NYK vs. MIA",
            ),
            make_game_row(
                Player_ID=456,
                Game_ID=None,
                GAME_DATE="2026-01-17",
                MATCHUP="GSW vs. PHX",
            ),
        ]
    )

    cleaned = clean_player_game_log(raw_df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["player_id"] == 123
    assert cleaned.iloc[0]["game_id"] == "001"