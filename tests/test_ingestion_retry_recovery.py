"""SCRUM-138: bounded retries, failure recovery and no duplicates, end to end.

Uses real PostgreSQL temporary tables and offline ESPN fixtures served through a
fake requests.get, so request_json's real retry loop runs.
"""
import copy
import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import psycopg
import pytest
import requests

from data.collection import espn
from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion import database_ingestion as ingestion
from data.ingestion import historical_backfill as backfill
from data.ingestion import incremental_refresh as refresh

PLAYER = 201939
SEASON = "2024-25"
FIXTURES = Path(__file__).with_name("fixtures")
PAYLOADS = {name: json.loads((FIXTURES / f"espn_{name}.json").read_text()) for name in ["gamelog", "summary"]}
REAL_REQUEST_JSON = espn.request_json  # conftest's espn_responses would replace it


class FlakyEspn:
    """Serves fixture payloads; each URL first fails `failures_per_url` times with `error`."""

    def __init__(self, failures_per_url=0, error=requests.ConnectionError):
        self.failures_per_url = failures_per_url
        self.error = error
        self.calls = {}

    def __call__(self, url, params=None, timeout=None):
        self.calls[url] = self.calls.get(url, 0) + 1
        if self.calls[url] <= self.failures_per_url:
            raise self.error("simulated outage")
        name = "gamelog" if url.endswith("/gamelog") else "summary"
        return Mock(raise_for_status=Mock(), json=Mock(return_value=copy.deepcopy(PAYLOADS[name])))


@pytest.fixture
def db(monkeypatch):
    with psycopg.connect(ingestion.get_database_url(), autocommit=True) as connection:
        connection.execute(Path("database/schema.sql").read_text().replace("CREATE TABLE", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO teams (id, full_name, abbreviation) VALUES (1, 'Home', 'GSW'), (2, 'Away', 'LAC');
            INSERT INTO players (id, full_name, is_active, team_id) VALUES (201939, 'Test Player', TRUE, 1)
        """)
        for module in (refresh, backfill):
            monkeypatch.setattr(module.psycopg, "connect", lambda *args, **kwargs: nullcontext(connection))
        monkeypatch.setattr(espn, "request_json", REAL_REQUEST_JSON)
        espn.game_summary.cache_clear()
        yield connection
        espn.game_summary.cache_clear()


def stored(connection):
    return connection.execute("SELECT * FROM player_game_stats ORDER BY player_id, game_id").fetchall()


def use_espn(monkeypatch, fake):
    monkeypatch.setattr(espn.requests, "get", fake)
    espn.game_summary.cache_clear()
    return fake


def test_refresh_recovers_from_transient_outage_and_completes(db, monkeypatch, caplog):
    fake = use_espn(monkeypatch, FlakyEspn(failures_per_url=2))

    assert refresh.refresh_player(PLAYER, SEASON) == 0

    assert all(count == 3 for count in fake.calls.values())  # 2 failures + 1 success per URL
    assert len(stored(db)) == 1
    assert refresh.get_refresh_status(PLAYER, SEASON)["freshness"] == "fresh"
    assert "espn_request_retry" in caplog.text and "error_type=ConnectionError" in caplog.text


def test_persistent_outage_stops_at_retry_limit_and_preserves_history(db, monkeypatch, caplog):
    use_espn(monkeypatch, FlakyEspn())
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    before = stored(db)

    fake = use_espn(monkeypatch, FlakyEspn(failures_per_url=99, error=requests.Timeout))
    assert refresh.refresh_player(PLAYER, SEASON) == 1

    assert list(fake.calls.values()) == [espn.RETRY_ATTEMPTS]  # first URL only; no infinite loop
    assert stored(db) == before
    status = refresh.get_refresh_status(PLAYER, SEASON)
    assert status["freshness"] == "failed" and status["error_type"] == "Timeout"
    assert status["last_successful_refresh"] is not None
    assert "espn_request_failed path=athletes/3975/gamelog attempts=3" in caplog.text


def test_repeated_refresh_after_recovery_adds_no_duplicates(db, monkeypatch):
    use_espn(monkeypatch, FlakyEspn(failures_per_url=1))
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    first = stored(db)
    use_espn(monkeypatch, FlakyEspn(failures_per_url=1))
    assert refresh.refresh_player(PLAYER, SEASON) == 0
    assert stored(db) == first
    assert db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_backfill_rolls_back_a_malformed_season_and_recovers(db, monkeypatch):
    use_espn(monkeypatch, FlakyEspn())
    logs = fetch_player_game_log(PLAYER, SEASON)
    db.execute("INSERT INTO teams (id, full_name, abbreviation) VALUES (3, 'Other', 'OTH')")
    db.execute("INSERT INTO games (id, game_date, home_team_id, away_team_id) VALUES ('kept', '2024-12-01', 1, 3)")
    db.execute("INSERT INTO player_game_stats (player_id, game_id, minutes, points, rebounds, assists)"
               " VALUES (201939, 'kept', 30, 25, 5, 5)")
    before = stored(db)

    # A second row whose opponent is unknown: the whole season must roll back, including the valid row.
    bad_row = logs.iloc[[0]].assign(
        game_id="bad", matchup="GSW vs. XXX", game_date=pd.Timestamp(logs["game_date"].iloc[0]) + pd.Timedelta(days=1))
    monkeypatch.setattr(backfill, "fetch_player_game_log", Mock(return_value=pd.concat([logs, bad_row])))
    with pytest.raises(ValueError, match="rolled back"):
        backfill.ingest_player_season(PLAYER, SEASON)
    assert stored(db) == before
    assert db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1

    monkeypatch.setattr(backfill, "fetch_player_game_log", Mock(return_value=logs))
    games, stats = backfill.ingest_player_season(PLAYER, SEASON)
    assert games["failed"] == stats["failed"] == 0
    after_first = stored(db)
    assert len(after_first) == 2

    backfill.ingest_player_season(PLAYER, SEASON)  # rerun: upsert, no duplicates
    assert stored(db) == after_first
