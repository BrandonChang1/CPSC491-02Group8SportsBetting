import pandas as pd

from data.processing.prediction_readiness import readiness_checks, readiness_report

HOME, AWAY = 1610612744, 1610612747


def make_rows():
    """One player, three games: two away at LAL then one home against LAL."""
    return pd.DataFrame(
        [
            {"player_id": 201939, "game_id": "001", "game_date": pd.Timestamp("2025-10-21"), "minutes": 32,
             "points": 23, "rebounds": 4, "assists": 7, "plus_minus": 2, "opponent_team_id": AWAY,
             "is_home": False, "recent_minutes_avg": None, "home_team_id": AWAY, "away_team_id": HOME},
            {"player_id": 201939, "game_id": "002", "game_date": pd.Timestamp("2025-10-23"), "minutes": 36,
             "points": 25, "rebounds": 5, "assists": 6, "plus_minus": 4, "opponent_team_id": AWAY,
             "is_home": False, "recent_minutes_avg": 32.0, "home_team_id": AWAY, "away_team_id": HOME},
            {"player_id": 201939, "game_id": "003", "game_date": pd.Timestamp("2025-10-25"), "minutes": 30,
             "points": 20, "rebounds": 3, "assists": 8, "plus_minus": -1, "opponent_team_id": AWAY,
             "is_home": True, "recent_minutes_avg": 34.0, "home_team_id": HOME, "away_team_id": AWAY},
        ]
    )


def failing(rows):
    return {result["check"]: result["failing_rows"] for result in readiness_checks(rows) if result["failing_rows"]}


def test_clean_rows_are_ready_in_the_served_feature_schema():
    report = readiness_report(make_rows())

    assert report["ready"]
    assert report["feature_schema_problems"] == []
    assert report["coverage"]["rows_with_all_features"] == 2


def test_missing_required_fields_fail_completeness():
    rows = make_rows()
    rows.loc[1, ["points", "minutes", "opponent_team_id"]] = None
    rows["is_home"] = rows["is_home"].astype(object)
    rows.loc[2, "is_home"] = None

    assert failing(rows) == {
        "points present": 1,
        "minutes present": 1,
        "is_home present": 1,
        "opponent_team_id present": 1,
        # Row 3's stored average no longer matches once row 2's minutes are gone.
        "recent_minutes_avg equals the prior-5-game minutes average": 1,
    }
    assert not readiness_report(rows)["ready"]


def test_opponent_that_contradicts_home_away_fails():
    rows = make_rows()
    rows.loc[2, "is_home"] = False

    assert failing(rows) == {"opponent/home-away agree with the game's teams": 1}


def test_recent_minutes_must_use_only_prior_games():
    rows = make_rows()
    # Includes the current game's 30 minutes: leakage.
    rows.loc[2, "recent_minutes_avg"] = (32 + 36 + 30) / 3
    rows.loc[0, "recent_minutes_avg"] = 32.0

    assert failing(rows) == {
        "recent_minutes_avg equals the prior-5-game minutes average": 1,
        "recent_minutes_avg empty on a player's first game": 1,
    }


def test_out_of_range_values_and_duplicate_dates_fail_validity():
    rows = make_rows()
    rows.loc[0, "points"] = -2
    rows.loc[1, "minutes"] = 95
    rows.loc[2, "game_date"] = rows.loc[1, "game_date"]

    result = failing(rows)

    assert result["points is a whole number 0-100"] == 1
    assert result["minutes within 0-70"] == 1
    assert result["one row per player per game date"] == 2
