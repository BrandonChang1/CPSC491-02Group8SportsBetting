import pandas as pd
import pytest

from data.processing.modeling_features import (
    add_modeling_context,
    parse_player_matchup,
)


def test_parse_player_matchup_home():
    team, opponent, is_home = parse_player_matchup(
        "GSW vs. LAL"
    )

    assert team == "GSW"
    assert opponent == "LAL"
    assert is_home is True


def test_parse_player_matchup_away():
    team, opponent, is_home = parse_player_matchup(
        "GSW @ POR"
    )

    assert team == "GSW"
    assert opponent == "POR"
    assert is_home is False


def test_parse_player_matchup_invalid():
    with pytest.raises(ValueError):
        parse_player_matchup("GSW LAL")


def test_add_modeling_context():
    game_logs = pd.DataFrame(
        [
            {
                "player_id": 123,
                "game_id": "001",
                "game_date": pd.Timestamp("2026-01-01"),
                "matchup": "GSW vs. LAL",
                "minutes": 30,
            },
            {
                "player_id": 123,
                "game_id": "002",
                "game_date": pd.Timestamp("2026-01-03"),
                "matchup": "GSW @ POR",
                "minutes": 34,
            },
            {
                "player_id": 123,
                "game_id": "003",
                "game_date": pd.Timestamp("2026-01-05"),
                "matchup": "GSW vs. BOS",
                "minutes": 38,
            },
        ]
    )

    result = add_modeling_context(game_logs)

    assert result.iloc[0]["opponent_abbreviation"] == "LAL"
    assert result.iloc[0]["is_home"] == True

    assert result.iloc[1]["opponent_abbreviation"] == "POR"
    assert result.iloc[1]["is_home"] == False

    assert pd.isna(
        result.iloc[0]["recent_minutes_avg"]
    )

    assert result.iloc[1]["recent_minutes_avg"] == 30

    assert result.iloc[2]["recent_minutes_avg"] == 32