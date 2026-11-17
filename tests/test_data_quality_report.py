"""SCRUM-136: the data-quality report detects planted bad rows and never writes.

Each test plants rows inside a transaction that is rolled back, and compares
failing counts against a baseline taken in the same transaction, so it works on
the seeded CI database or a populated development database.
"""
import os

import psycopg
import pytest
from dotenv import load_dotenv

from data.processing.data_quality_report import build_report, to_markdown

load_dotenv()

HOME, AWAY, OTHER = 990001, 990002, 990003
PLAYER = 990101


@pytest.fixture
def connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL is not set. The data-quality report tests require the test database.")
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO teams (id, full_name, abbreviation) VALUES"
            " (%s, 'QA Home', 'QAH'), (%s, 'QA Away', 'QAA'), (%s, 'QA Other', 'QAO')",
            (HOME, AWAY, OTHER),
        )
        conn.execute("INSERT INTO players (id, full_name, is_active) VALUES (%s, 'QA Player', true)", (PLAYER,))
        yield conn
        conn.rollback()


def add_game(conn, game_id, game_date, home=HOME, away=AWAY):
    conn.execute("INSERT INTO games (id, game_date, home_team_id, away_team_id) VALUES (%s, %s, %s, %s)",
                 (game_id, game_date, home, away))


def add_stats(conn, game_id, **overrides):
    """A clean home-game stat line; overrides plant the defect under test."""
    row = {
        "player_id": PLAYER, "game_id": game_id, "minutes": 30, "points": 20, "rebounds": 6, "assists": 4,
        "matchup": "QAH vs. QAA", "win_loss": "W", "opponent_team_id": AWAY, "is_home": True,
        "field_goals_made": 8, "field_goals_attempted": 16, "field_goal_pct": 0.5,
        "three_pointers_made": 2, "three_pointers_attempted": 5, "three_point_pct": 0.4,
        "free_throws_made": 2, "free_throws_attempted": 2, "free_throw_pct": 1.0,
        "offensive_rebounds": 2, "defensive_rebounds": 4,
        **overrides,
    }
    columns = ", ".join(row)
    conn.execute(f"INSERT INTO player_game_stats ({columns}) VALUES ({', '.join(['%s'] * len(row))})",
                 list(row.values()))


def failing(report):
    return {c["check"]: c["failing_rows"] for c in report["checks"]}


def new_failures(conn, plant):
    """Checks whose failing count went up after plant(conn), with the increase."""
    before = failing(build_report(conn))
    plant(conn)
    after = failing(build_report(conn))
    return {name: after[name] - before[name] for name in after if after[name] != before[name]}


def test_clean_rows_add_no_failures(connection):
    def plant(conn):
        add_game(conn, "QA1", "2025-01-01")
        add_stats(conn, "QA1")

    assert new_failures(connection, plant) == {}


def test_detects_duplicate_player_game_date_and_reversed_game(connection):
    def plant(conn):
        add_game(conn, "QA1", "2025-01-01")
        add_game(conn, "QA2", "2025-01-01", home=AWAY, away=HOME)  # same matchup stored twice
        add_stats(conn, "QA1")
        add_stats(conn, "QA2", is_home=False, matchup="QAH @ QAA")

    assert new_failures(connection, plant) == {
        "one stat row per player per game date": 1,
        "one game per date and team pair (either home/away order)": 1,
        "one game per team per date": 2,
        # QA2 is the player's second stored game, so its NULL recent_minutes_avg is also wrong.
        "recent_minutes_avg equals the prior-5-game minutes average": 1,
    }


def test_detects_missing_required_fields(connection):
    def plant(conn):
        add_game(conn, "QA1", "2025-01-01")
        add_stats(conn, "QA1", points=None, is_home=None, win_loss=None)

    found = new_failures(connection, plant)
    assert found["stat row has minutes, points, rebounds and assists"] == 1
    assert found["stat row has opponent_team_id and is_home"] == 1
    assert found["stat row has matchup and win_loss"] == 1


def test_detects_invalid_numeric_statistics(connection):
    def plant(conn):
        add_game(conn, "QA1", "2025-01-01")
        add_game(conn, "QA2", "2025-01-02")
        add_game(conn, "QA3", "2025-01-03")
        add_stats(conn, "QA1", minutes=-1, points=150)
        add_stats(conn, "QA2", rebounds=7, field_goals_made=20, field_goal_pct=1.25)
        add_stats(conn, "QA3", field_goal_pct=0.9, minutes=0)

    found = new_failures(connection, plant)
    assert found["counting stats are not negative"] == 1
    assert found["points within 0-100"] == 1
    assert found["made shots do not exceed attempts"] == 1
    assert found["shooting percentages within 0-1"] == 1
    assert found["shooting percentages equal made / attempted"] == 1
    assert found["points equal 2*FGM + 3PM + FTM"] == 2
    assert found["rebounds equal offensive + defensive rebounds"] == 1
    assert found["points, rebounds and assists are zero when minutes are zero"] == 1


def test_detects_inconsistent_player_game_relationships(connection):
    def plant(conn):
        add_game(conn, "QA1", "2025-01-01")
        add_game(conn, "QA2", "2999-01-01", home=OTHER, away=AWAY)
        add_stats(conn, "QA1", opponent_team_id=OTHER)  # opponent not in this game
        add_stats(conn, "QA2", is_home=False)  # matchup names QAH, which didn't play QA2

    found = new_failures(connection, plant)
    assert found["opponent and is_home agree with the game's teams"] == 2
    assert found["matchup's team abbreviation is one of the game's teams"] == 1
    assert found["stat rows are for games on or before today"] == 1


def test_detects_cross_row_inconsistencies(connection):
    teammate = PLAYER + 1

    def plant(conn):
        conn.execute("INSERT INTO players (id, full_name, is_active) VALUES (%s, 'QA Teammate', true)", (teammate,))
        add_game(conn, "QA1", "2025-01-01")
        add_game(conn, "QA2", "2025-01-02")
        add_game(conn, "QA3", "2025-01-03")
        add_stats(conn, "QA1")
        add_stats(conn, "QA1", player_id=teammate, win_loss="L")  # same side, different result
        add_stats(conn, "QA2", recent_minutes_avg=30)
        add_stats(conn, "QA2", player_id=teammate, is_home=False, opponent_team_id=HOME,
                  matchup="QAA @ QAH", recent_minutes_avg=30)  # both sides won
        add_stats(conn, "QA3", matchup="QAH @ QAA", recent_minutes_avg=30)  # '@' but is_home

    found = new_failures(connection, plant)
    assert found == {
        "teammates in a game agree on win_loss, matchup and opponent": 1,
        "home and away sides of a game have opposite results": 1,  # QA2: both sides won
        "matchup 'vs.' / '@' agrees with is_home": 1,
    }


def test_detects_recent_minutes_avg_not_matching_stored_history(connection):
    def plant(conn):
        for day, minutes, recent in [(1, 40, None), (2, 40, 40.0), (3, 20, 40.0), (4, 30, 20.0)]:
            add_game(conn, f"QA{day}", f"2025-01-0{day}")
            add_stats(conn, f"QA{day}", minutes=minutes, recent_minutes_avg=recent)

    # Game 4 should be mean(40, 40, 20) = 33.33; 20.0 is a batch-local value.
    assert new_failures(connection, plant) == {"recent_minutes_avg equals the prior-5-game minutes average": 1}


def test_error_failures_fail_the_report_and_are_counted(connection):
    add_game(connection, "QA1", "2025-01-01")
    add_stats(connection, "QA1", points=150)

    report = build_report(connection)

    assert not report["passed"]
    assert report["summary"]["invalid_stat_records"] >= 1
    failed = next(c for c in report["checks"] if c["check"] == "points within 0-100")
    assert {"player_id": str(PLAYER), "game_id": "QA1"} in failed["samples"]
    assert "**FAIL**" in to_markdown(report)


def test_report_runs_in_a_read_only_transaction():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        report = build_report(conn)  # would raise ReadOnlySqlTransaction if it wrote
        conn.rollback()
    assert report["summary"]["checks_run"] == len(report["checks"])
