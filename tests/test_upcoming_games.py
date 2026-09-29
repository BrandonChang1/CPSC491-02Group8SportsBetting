from datetime import datetime, timezone

from scripts.upcoming_games import normalize_upcoming_games, season_for_date, seasons_for_window


def sample_game(game_id, tipoff, status=1):
    return {
        "gameId": game_id,
        "gameStatus": status,
        "gameStatusText": "Scheduled" if status == 1 else "Final",
        "gameDateTimeUTC": tipoff,
        "awayTeam_teamCity": "Los Angeles",
        "awayTeam_teamName": "Lakers",
        "awayTeam_teamTricode": "LAL",
        "homeTeam_teamCity": "Denver",
        "homeTeam_teamName": "Nuggets",
        "homeTeam_teamTricode": "DEN",
        "arenaName": "Ball Arena",
        "arenaCity": "Denver",
        "arenaState": "CO",
    }


def test_season_for_date():
    assert season_for_date(datetime(2026, 9, 21, tzinfo=timezone.utc)) == "2026-27"
    assert season_for_date(datetime(2027, 2, 1, tzinfo=timezone.utc)) == "2026-27"


def test_window_can_cross_season_boundary():
    start = datetime(2027, 6, 25, tzinfo=timezone.utc)
    end = datetime(2027, 7, 9, tzinfo=timezone.utc)
    assert seasons_for_window(start, end) == ["2026-27", "2027-28"]


def test_only_future_scheduled_games_within_fourteen_days_are_returned():
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    rows = [
        sample_game("past", "2026-09-21T17:00:00Z"),
        sample_game("tomorrow", "2026-09-22T18:00:00Z"),
        sample_game("day14", "2026-10-05T17:59:59Z"),
        sample_game("too-late", "2026-10-05T18:00:01Z"),
        sample_game("already-final", "2026-09-25T18:00:00Z", status=3),
    ]

    result = normalize_upcoming_games(rows, now)

    assert [game["gameId"] for game in result] == ["tomorrow", "day14"]
    assert result[0]["awayTeam"]["name"] == "Los Angeles Lakers"
    assert result[0]["homeTeam"]["name"] == "Denver Nuggets"
