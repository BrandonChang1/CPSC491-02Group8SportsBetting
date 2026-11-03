"""Controlled ESPN responses: no network or production database required."""

from unittest.mock import Mock

import pytest
import requests

from data.collection import espn


def test_regular_season_only_and_duplicate_events(espn_responses):
    events = espn.player_events(201939, "2024-25")
    assert list(events) == ["401705764"]
    assert events["401705764"]["stats"]["points"] == "36"


def test_team_ids_and_abbreviations_preserved(espn_responses):
    teams = espn.get_teams()
    assert len(teams) == 30
    warriors = next(t for t in teams if t["espn_id"] == "9")
    assert warriors["id"] == 1610612744
    assert warriors["abbreviation"] == "GSW"
    assert next(t for t in teams if t["espn_id"] == "26")["abbreviation"] == "UTA"


def test_roster_uses_existing_curry_identity(espn_responses, monkeypatch):
    warriors = next(t for t in espn.get_teams() if t["abbreviation"] == "GSW")
    with monkeypatch.context() as patch:
        patch.setattr(espn, "get_teams", lambda: [warriors])
        roster = espn.get_players()
    assert roster == [
        {
            "id": 201939,
            "espn_id": "3975",
            "full_name": "Stephen Curry",
            "first_name": "Stephen",
            "last_name": "Curry",
            "is_active": True,
            "team_id": 1610612744,
        }
    ]


def test_unknown_team_refuses_mapping(espn_responses):
    espn_responses["teams"]["sports"][0]["leagues"][0]["teams"][0]["team"][
        "abbreviation"
    ] = "UNKNOWN"
    with pytest.raises(ValueError, match="Unknown ESPN team mapping"):
        espn.get_teams()


def test_each_roster_keeps_its_own_team(espn_responses, monkeypatch):
    teams = espn.get_teams()[:2]
    with monkeypatch.context() as patch:
        patch.setattr(espn, "get_teams", lambda: teams)
        patch.setattr(espn, "_roster", lambda team: [{
            "id": str(90000000 + team["id"]),
            "displayName": team["full_name"],
            "firstName": "Synthetic", "lastName": "Player",
        }])
        roster = espn.get_players()
    assert len(roster) == 2
    assert [(p["full_name"], p["team_id"]) for p in roster] == [
        (team["full_name"], team["id"]) for team in teams
    ]


def test_duplicate_legacy_names_are_rejected(monkeypatch):
    monkeypatch.setattr(
        espn, "LEGACY", {"players": {"1": "Same Name", "2": "Same Name"}}
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        espn.legacy_player_id({"id": "100", "displayName": "Same Name"})


def test_reviewed_brandon_williams_mapping():
    assert (
        espn.legacy_player_id({"id": "4397040", "displayName": "Brandon Williams"})
        == 1630314
    )


def test_new_player_ids_cannot_collide_with_legacy_ids():
    athlete = {"id": "99999999", "displayName": "Synthetic New Player"}
    internal = espn.legacy_player_id(athlete)
    assert internal == espn.PLAYER_ID_OFFSET + 99999999
    assert espn.espn_player_id(internal) == "99999999"
    assert str(internal) not in espn.LEGACY["players"]


def test_mapping_snapshot_has_unique_ids_and_matching_names():
    assert len({p["espn_id"] for p in espn.PLAYER_IDS.values()}) == len(espn.PLAYER_IDS)
    for nba_id, player in espn.PLAYER_IDS.items():
        assert espn.normalize_name(
            espn.LEGACY["players"][nba_id]
        ) == espn.normalize_name(player["name"])


@pytest.mark.parametrize("season", ["2025", "2025-27", "invalid"])
def test_bad_season_rejected(season):
    with pytest.raises(ValueError, match="YYYY-YY"):
        espn.season_end_year(season)


def test_unknown_legacy_id_is_not_sent_as_an_espn_id():
    with pytest.raises(ValueError, match="No verified ESPN mapping"):
        espn.espn_player_id(999999999)


def test_boxscore_preserves_full_statistics(summary):
    row = espn.player_boxscore(summary, "3975", 201939)
    assert row["Game_ID"] == "espn:401705764"
    assert row["Player_ID"] == 201939
    assert row["PTS"] == 36
    assert row["FGM"] == 10
    assert row["FGA"] == 20
    assert row["FG_PCT"] == 0.5
    assert row["FG3_PCT"] == 0.583
    assert row["FT_PCT"] == 1
    assert row["OREB"] + row["DREB"] == row["REB"] == 3
    assert row["MATCHUP"] == "GSW vs. LAC"
    assert row["GAME_DATE"] == "2025-04-13"


def test_game_date_uses_eastern_calendar_day():
    assert espn.game_date("2025-01-16T02:00Z") == "2025-01-15"


def test_incomplete_game_skipped(summary):
    summary["header"]["competitions"][0]["status"]["type"]["completed"] = False
    assert espn.player_boxscore(summary, "3975", 201939) is None


def test_missing_athlete_fails_instead_of_silent_partial_data(summary):
    with pytest.raises(ValueError, match="missing athlete"):
        espn.player_boxscore(summary, "not-curry", 201939)


def test_bad_shooting_values_rejected(summary):
    group = next(
        g
        for t in summary["boxscore"]["players"]
        for g in t["statistics"]
        if any(a["athlete"]["id"] == "3975" for a in g["athletes"])
    )
    curry = next(a for a in group["athletes"] if a["athlete"]["id"] == "3975")
    curry["stats"][group["labels"].index("FG")] = "20-10"
    with pytest.raises(ValueError, match="Invalid shooting"):
        espn.player_boxscore(summary, "3975", 201939)


def test_http_timeout_and_failure_propagate(monkeypatch):
    get = Mock(side_effect=requests.Timeout("timeout"))
    monkeypatch.setattr(espn.requests, "get", get)
    with pytest.raises(requests.Timeout):
        espn.request_json(espn.SITE, "teams")
    get.assert_called_once_with(f"{espn.SITE}/teams", params={}, timeout=15)
    get.side_effect = None
    get.return_value.raise_for_status.side_effect = requests.HTTPError("503")
    with pytest.raises(requests.HTTPError):
        espn.request_json(espn.SITE, "teams")


def test_invalid_payload_rejected(monkeypatch):
    monkeypatch.setattr(
        espn.requests,
        "get",
        Mock(return_value=Mock(json=lambda: {"error": "unavailable"})),
    )
    with pytest.raises(ValueError, match="Invalid ESPN response"):
        espn.request_json(espn.SITE, "teams")


def test_zero_attempts_and_clock_minutes(summary):
    group = next(
        g
        for t in summary["boxscore"]["players"]
        for g in t["statistics"]
        if any(a["athlete"]["id"] == "3975" for a in g["athletes"])
    )
    curry = next(a for a in group["athletes"] if a["athlete"]["id"] == "3975")
    curry["stats"][group["labels"].index("FT")] = "0-0"
    curry["stats"][group["labels"].index("MIN")] = "32:30"
    row = espn.player_boxscore(summary, "3975", 201939)
    assert row["FT_PCT"] == 0
    assert row["MIN"] == 33


def test_team_history_uses_espn_scores_and_totals(monkeypatch, summary):
    summary["boxscore"]["teams"] = [
        {
            "team": {"id": "9"},
            "statistics": [
                {"name": "totalRebounds", "displayValue": "40"},
                {"name": "assists", "displayValue": "20"},
            ],
        }
    ]
    monkeypatch.setattr(
        espn,
        "request_json",
        lambda *args, **kwargs: {
            "events": [
                {
                    "id": "401705764",
                    "date": "2025-04-13T19:30Z",
                    "competitions": [{"status": {"type": {"completed": True}}}],
                }
            ]
        },
    )
    monkeypatch.setattr(espn, "game_summary", lambda event_id: summary)
    result = espn.team_game_log({"espn_id": "9", "abbreviation": "GSW"}, "2024-25")
    assert result[0]["REB"] == 40
    assert result[0]["AST"] == 20
    assert result[0]["MATCHUP"] == "GSW vs. LAC"


def test_did_not_play_is_skipped_without_zero_statistics(summary):
    for team in summary["boxscore"]["players"]:
        for group in team["statistics"]:
            for entry in group["athletes"]:
                if entry["athlete"]["id"] == "3975":
                    entry["didNotPlay"] = True
                    entry["stats"] = []
    assert espn.player_boxscore(summary, "3975", 201939) is None
