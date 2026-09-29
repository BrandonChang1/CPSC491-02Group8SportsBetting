import pytest

from data.ingestion.database_ingestion import parse_matchup


def test_parse_matchup_home_game():
    home_team, away_team = parse_matchup("GSW vs. LAL")

    assert home_team == "GSW"
    assert away_team == "LAL"


def test_parse_matchup_away_game():
    home_team, away_team = parse_matchup("GSW @ POR")

    assert home_team == "POR"
    assert away_team == "GSW"


def test_parse_matchup_invalid_format():
    with pytest.raises(ValueError):
        parse_matchup("GSW LAL")