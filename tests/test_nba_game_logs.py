from unittest.mock import MagicMock, patch

import pandas as pd

from data.collection.nba_game_logs import fetch_player_game_log


@patch("data.collection.nba_game_logs.playergamelog.PlayerGameLog")
def test_fetch_player_game_log_returns_cleaned_data(mock_player_game_log):
    raw_df = pd.DataFrame(
        {
            "Player_ID": [123],
            "Game_ID": ["001"],
            "GAME_DATE": ["2026-01-15"],
            "MATCHUP": ["LAL vs. BOS"],
            "WL": ["W"],
            "MIN": ["35"],
            "FGM": ["10"],
            "FGA": ["20"],
            "FG_PCT": ["0.500"],
            "FG3M": ["4"],
            "FG3A": ["9"],
            "FG3_PCT": ["0.444"],
            "FTM": ["4"],
            "FTA": ["5"],
            "FT_PCT": ["0.800"],
            "OREB": ["1"],
            "DREB": ["6"],
            "REB": ["7"],
            "AST": ["9"],
            "STL": ["2"],
            "BLK": ["1"],
            "TOV": ["3"],
            "PF": ["2"],
            "PTS": ["28"],
            "PLUS_MINUS": ["12"],
        }
    )

    mock_response = MagicMock()
    mock_response.get_data_frames.return_value = [raw_df]
    mock_player_game_log.return_value = mock_response

    result = fetch_player_game_log(
        player_id=123,
        season="2025-26",
    )

    assert len(result) == 1

    assert result.iloc[0]["player_id"] == 123
    assert result.iloc[0]["game_id"] == "001"

    assert result.iloc[0]["minutes"] == 35
    assert result.iloc[0]["points"] == 28

    assert result.iloc[0]["field_goals_made"] == 10
    assert result.iloc[0]["field_goals_attempted"] == 20
    assert result.iloc[0]["field_goal_pct"] == 0.500

    assert result.iloc[0]["three_pointers_made"] == 4
    assert result.iloc[0]["three_pointers_attempted"] == 9
    assert result.iloc[0]["three_point_pct"] == 0.444

    assert result.iloc[0]["free_throws_made"] == 4
    assert result.iloc[0]["free_throws_attempted"] == 5
    assert result.iloc[0]["free_throw_pct"] == 0.800

    assert result.iloc[0]["offensive_rebounds"] == 1
    assert result.iloc[0]["defensive_rebounds"] == 6
    assert result.iloc[0]["rebounds"] == 7

    assert result.iloc[0]["assists"] == 9
    assert result.iloc[0]["steals"] == 2
    assert result.iloc[0]["blocks"] == 1
    assert result.iloc[0]["turnovers"] == 3
    assert result.iloc[0]["personal_fouls"] == 2
    assert result.iloc[0]["plus_minus"] == 12

    mock_player_game_log.assert_called_once_with(
        player_id=123,
        season="2025-26",
        season_type_all_star="Regular Season",
    )


@patch("data.collection.nba_game_logs.playergamelog.PlayerGameLog")
def test_fetch_player_game_log_handles_empty_response(mock_player_game_log):
    raw_df = pd.DataFrame()

    mock_response = MagicMock()
    mock_response.get_data_frames.return_value = [raw_df]
    mock_player_game_log.return_value = mock_response

    result = fetch_player_game_log(
        player_id=123,
        season="2025-26",
    )

    assert result.empty