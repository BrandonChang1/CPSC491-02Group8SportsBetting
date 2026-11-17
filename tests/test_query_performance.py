"""SCRUM-139: the query-performance report measures the real backend SQL and the search index exists."""
import os

import psycopg
import pytest
from dotenv import load_dotenv

from scripts.query_performance import build_report, js_query, queries, to_markdown

load_dotenv()


def test_every_backend_query_is_extracted_with_named_params():
    # Fails loudly if a backend query is edited so the benchmark can no longer find it.
    found = queries(player_id=1)
    assert len(found) == 12
    for name, _, sql, params in found:
        assert "$" not in sql, name
        assert sql.count("%(") >= len(params), name


def test_ambiguous_marker_is_rejected():
    with pytest.raises(ValueError, match="found 2"):
        js_query("backend/app/services/fastPlayerLookup.js", "LIMIT 10")  # also matches LIMIT 100


@pytest.fixture
def connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL is not set. Query-performance tests require the test database.")
    with psycopg.connect(database_url) as conn:
        yield conn


def test_report_runs_read_only_and_records_plans(connection):
    connection.execute("SET TRANSACTION READ ONLY")
    report = build_report(connection, runs=1)
    connection.rollback()

    assert len(report["results"]) == 12
    for result in report["results"]:
        assert result["median_ms"] >= 0 and result["scans"] and len(result["result_sha256"]) == 16
    assert "| player search (typeahead) |" in to_markdown(report)


def test_player_search_trigram_index_exists_and_serves_ilike(connection):
    index = connection.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'players_full_name_trgm'"
    ).fetchone()
    assert index and "gin_trgm_ops" in index[0]

    # Small CI tables may favour a sequential scan, so check the index is usable rather than chosen.
    connection.execute("SET LOCAL enable_seqscan = off")
    plan = connection.execute("EXPLAIN SELECT id FROM players WHERE full_name ILIKE '%lebron%'").fetchall()
    assert any("players_full_name_trgm" in line for (line,) in plan)
    connection.rollback()
