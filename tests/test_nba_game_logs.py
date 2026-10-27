"""ESPN data keeps the existing cleaned game-log contract."""

from data.collection.nba_game_logs import fetch_player_game_log


def test_fetch_player_game_log_returns_cleaned_data(espn_responses):
    result = fetch_player_game_log(201939, "2024-25")
    assert len(result) == 1
    row = result.iloc[0]
    assert row["player_id"] == 201939
    assert row["game_id"] == "espn:401705764"
    assert row["points"] == 36
    assert row["field_goals_made"] == 10
    assert row["field_goals_attempted"] == 20
    assert row["field_goal_pct"] == 0.5
    assert row["three_pointers_made"] == 7
    assert row["free_throws_made"] == 9
    assert row["rebounds"] == 3
    assert row["assists"] == 6
    assert row["minutes"] == 38


def test_fetch_player_game_log_handles_empty_response(espn_responses):
    espn_responses["gamelog"]["seasonTypes"] = []
    assert fetch_player_game_log(201939, "2024-25").empty
