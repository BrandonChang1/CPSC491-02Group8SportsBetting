"""Read-only PostgreSQL query-performance report for the app's main player/game queries (SCRUM-139).

    python -m scripts.query_performance                    # Markdown to stdout
    python -m scripts.query_performance --runs 50 --json   # JSON to stdout
    python -m scripts.query_performance --output docs/evidence/scrum-139/after.md

Backend SQL is read straight out of the JS source, so this measures what the API
actually runs. Each query runs under EXPLAIN (ANALYZE, BUFFERS) several times and
reports the median execution time, the scans used, and a hash of the returned rows
so results can be compared before and after an optimization.
"""
import argparse
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

import psycopg

from data.ingestion.database_ingestion import get_database_url
from data.ingestion.incremental_refresh import FRESHNESS_QUERY
from data.ingestion.monitoring import run
from data.processing.prediction_readiness import READINESS_QUERY

ROOT = Path(__file__).resolve().parents[1]
JS_QUERY = re.compile(r"pool\.query\(\s*(`|\")(.*?)\1", re.DOTALL)


def js_query(path, marker):
    """The one pool.query SQL literal in `path` containing `marker`, converted to psycopg named params."""
    matches = [sql for _, sql in JS_QUERY.findall((ROOT / path).read_text()) if marker in sql]
    if len(matches) != 1:
        raise ValueError(f"Expected one query containing {marker!r} in {path}, found {len(matches)}")
    return re.sub(r"\$(\d+)", r"%(p\1)s", matches[0].replace("%", "%%"))


def queries(player_id):
    """(name, used by, sql, params). $1, $2... in backend SQL become p1, p2..."""
    lookup = "backend/app/services/fastPlayerLookup.js"
    players = "backend/app/routes/players.js"
    return [
        ("player search (typeahead)", f"{lookup} searchPlayersInDatabase",
         js_query(lookup, "ILIKE $2"), {"p1": "%lebron%", "p2": "lebron%"}),
        ("player search (common term)", f"{lookup} searchPlayersInDatabase",
         js_query(lookup, "ILIKE $2"), {"p1": "%james%", "p2": "james%"}),
        ("player list search", f"{players} GET /players?search=",
         js_query(players, "WHERE full_name ILIKE"), {"p1": "%james%", "p2": 0, "p3": 50}),
        ("player details", f"{players} GET /players/:id",
         js_query(players, "LEFT JOIN teams t ON t.id = p.team_id"), {"p1": player_id}),
        ("recent game log", f"{lookup} getPlayerStatsFromDatabase",
         js_query(lookup, "LIMIT 100"), {"p1": player_id}),
        ("paged game history", f"{players} GET /players/:id/games",
         js_query(players, "g.id AS game_id"), {"p1": player_id, "p2": 0, "p3": 10}),
        ("points history (prediction)", "backend/app/services/prediction.js",
         js_query("backend/app/services/prediction.js", "pgs.points IS NOT NULL"), {"p1": player_id}),
        ("points + minutes history", "backend/app/routes/predictions.js",
         js_query("backend/app/routes/predictions.js", "ORDER BY g.game_date ASC"), {"p1": player_id}),
        ("team recent records", "backend/app/services/teamWinPrediction.js",
         js_query("backend/app/services/teamWinPrediction.js", "team_games"), {}),
        ("team rotation estimates", "backend/app/services/treeTeamPrediction.js",
         js_query("backend/app/services/treeTeamPrediction.js", "rotation"), {}),
        ("modeling/readiness dataset", "data/processing/prediction_readiness.py",
         READINESS_QUERY, {}),
        ("database freshness", "backend /health/freshness, incremental_refresh --status",
         FRESHNESS_QUERY, {"player_id": None, "season": None, "max_age_hours": 48}),
    ]


def plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from plan_nodes(child)


def measure(connection, name, used_by, sql, params, runs):
    times, plan = [], None
    for _ in range(runs + 1):  # first run warms the cache and is discarded
        plan = connection.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", params).fetchone()[0][0]
        times.append(plan["Execution Time"])
    rows = connection.execute(sql, params).fetchall()
    nodes = list(plan_nodes(plan["Plan"]))
    scans = sorted({f"{n['Node Type']} on {n.get('Index Name') or n['Relation Name']}"
                    for n in nodes if "Relation Name" in n})
    return {
        "query": name,
        "used_by": used_by,
        "median_ms": round(statistics.median(times[1:]), 3),
        "max_ms": round(max(times[1:]), 3),
        "planning_ms": round(plan["Planning Time"], 3),
        "rows": len(rows),
        "buffers": plan["Plan"].get("Shared Hit Blocks", 0) + plan["Plan"].get("Shared Read Blocks", 0),
        "scans": scans,
        "seq_scans": sorted({n["Relation Name"] for n in nodes if n["Node Type"] == "Seq Scan"}),
        # Ordered rows, so a plan change that reorders or drops results shows up as a different hash.
        "result_sha256": hashlib.sha256(repr(rows).encode()).hexdigest()[:16],
    }


def build_report(connection, runs):
    player_id = connection.execute(
        "SELECT player_id FROM player_game_stats GROUP BY player_id ORDER BY COUNT(*) DESC, player_id LIMIT 1"
    ).fetchone()
    if player_id is None:
        raise ValueError("player_game_stats is empty; load data before measuring")
    counts = {t: connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["players", "games", "player_game_stats", "ingestion_refresh_runs"]}
    indexes = [r[0] for r in connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
        " AND tablename IN ('players', 'games', 'player_game_stats', 'teams') ORDER BY 1")]
    return {
        "server_version": connection.execute("SHOW server_version").fetchone()[0],
        "runs_per_query": runs,
        "sample_player_id": player_id[0],
        "table_rows": counts,
        "indexes": indexes,
        "results": [measure(connection, *q, runs) for q in queries(player_id[0])],
    }


def to_markdown(report):
    lines = [
        "# PostgreSQL Query Performance",
        "",
        (f"PostgreSQL {report['server_version']}; median of {report['runs_per_query']} "
        f"`EXPLAIN (ANALYZE, BUFFERS)` runs after one warm-up; sample player `{report['sample_player_id']}`."),
        "",
        "Rows: " + ", ".join(f"{t} {n}" for t, n in report["table_rows"].items()) + "  ",
        "Indexes: " + ", ".join(f"`{i}`" for i in report["indexes"]),
        "",
        "| Query | Median ms | Max ms | Rows | Buffers | Scans | Result hash |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["results"]:
        lines.append(f"| {r['query']} | {r['median_ms']} | {r['max_ms']} | {r['rows']} | {r['buffers']} | "
                     f"{'<br>'.join(r['scans'])} | `{r['result_sha256']}` |")
    lines += ["", "Used by:", ""] + [f"- {r['query']}: `{r['used_by']}`" for r in report["results"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Read-only PostgreSQL query-performance report.")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    with psycopg.connect(get_database_url()) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        report = build_report(connection, args.runs)
        connection.rollback()
    text = json.dumps(report, indent=2) + "\n" if args.json else to_markdown(report)
    sys.stdout.write(text)
    if args.output:
        Path(args.output).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(main))
