"""SCRUM-140 regressions: corrected ingestion defects must not reappear.

recent_minutes_avg used to be computed from only the ingested batch, so a new
season's first games ignored games already stored (NULL, then a too-short
average) until a separate full recalculation ran. Real PostgreSQL temp tables.
"""
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import psycopg
import pytest

from data.ingestion import database_ingestion as ingestion
from data.processing.data_quality_report import build_report

PLAYER = 201939


def game_logs(prefix, games):
    """Cleaned game-log rows for PLAYER at home against LAC: games is [(date, minutes)]."""
    return pd.DataFrame([{
        "player_id": PLAYER, "game_id": f"{prefix}{i}", "game_date": pd.Timestamp(day), "matchup": "GSW vs. LAC",
        "win_loss": "W", "minutes": minutes, "points": 20, "rebounds": 5, "assists": 5, "plus_minus": 1,
        "field_goals_made": 8, "field_goals_attempted": 16, "field_goal_pct": 0.5,
        "three_pointers_made": 2, "three_pointers_attempted": 5, "three_point_pct": 0.4,
        "free_throws_made": 2, "free_throws_attempted": 2, "free_throw_pct": 1.0,
        "offensive_rebounds": 1, "defensive_rebounds": 4, "steals": 1, "blocks": 0,
        "turnovers": 2, "personal_fouls": 2,
    } for i, (day, minutes) in enumerate(games)])


PRIOR_SEASON = game_logs("old", [("2025-03-01", 40), ("2025-03-03", 40), ("2025-03-05", 40)])
NEW_SEASON = game_logs("new", [("2025-10-21", 20), ("2025-10-23", 30)])
# Prior 5 stored games: 10-21 -> mean(40, 40, 40); 10-23 -> mean(40, 40, 40, 20).
EXPECTED = [None, 40.0, 40.0, 40.0, 35.0]


@pytest.fixture
def db(monkeypatch):
    with psycopg.connect(ingestion.get_database_url(), autocommit=True) as connection:
        connection.execute(Path("database/schema.sql").read_text().replace("CREATE TABLE", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO teams (id, full_name, abbreviation) VALUES (1, 'Home', 'GSW'), (2, 'Away', 'LAC');
            INSERT INTO players (id, full_name, is_active) VALUES (201939, 'Test Player', TRUE)
        """)
        monkeypatch.setattr(ingestion.psycopg, "connect", lambda *args, **kwargs: nullcontext(connection))
        yield connection


def recent_minutes(connection):
    return [row[0] for row in connection.execute("""
        SELECT s.recent_minutes_avg FROM player_game_stats s JOIN games g ON g.id = s.game_id
        ORDER BY g.game_date, s.game_id
    """)]


def ingest(batch, connection=None):
    assert ingestion.ingest_games(batch, connection=connection)["failed"] == 0
    assert ingestion.ingest_player_game_stats(batch, connection=connection)["failed"] == 0


def test_new_season_batch_uses_previously_stored_games(db):
    ingest(PRIOR_SEASON)
    ingest(NEW_SEASON)  # autocommit path used by database_ingestion.main

    assert recent_minutes(db) == EXPECTED


def test_transactional_batch_is_consistent_when_committed(db):
    ingest(PRIOR_SEASON)
    with db.transaction():  # the caller's transaction, as historical_backfill uses
        ingest(NEW_SEASON, connection=db)

    assert recent_minutes(db) == EXPECTED


def test_out_of_order_backfill_recomputes_later_games(db):
    ingest(NEW_SEASON)
    assert recent_minutes(db) == [None, 20.0]
    ingest(PRIOR_SEASON)  # an older season arrives later and shifts the newer games' history

    assert recent_minutes(db) == EXPECTED


def test_data_quality_report_accepts_ingested_history(db):
    ingest(PRIOR_SEASON)
    ingest(NEW_SEASON)

    report = build_report(db)  # temp tables shadow the real ones for this session
    failed = {c["check"] for c in report["checks"] if not c["passed"] and c["severity"] == "error"}
    assert failed == set()
    assert report["table_counts"]["player_game_stats"] == 5
