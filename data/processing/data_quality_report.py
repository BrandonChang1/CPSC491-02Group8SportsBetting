"""Read-only data-quality report for the NBA PostgreSQL database.

Run from the repository root:
    python -m data.processing.data_quality_report              # Markdown to stdout
    python -m data.processing.data_quality_report --json       # JSON to stdout
    python -m data.processing.data_quality_report --output docs/evidence/scrum-136/data_quality_report.md

Runs inside a READ ONLY transaction, so it can be rerun without changing stored data.
Exits 1 if any error-severity check finds failing rows. See docs/data_quality_report.md.
"""
import argparse
import json
import sys
from datetime import UTC, datetime

import psycopg

from data.ingestion.database_ingestion import get_database_url
from data.ingestion.monitoring import run

SAMPLE_LIMIT = 5
MAX_MINUTES = 70  # Same bound as prediction_readiness: 4+ overtimes stay under this.
MAX_POINTS = 100
MAX_REBOUNDS = 60
MAX_ASSISTS = 40
PCT_TOLERANCE = 0.002  # Source percentages are rounded to 3 decimals.

# Every stat row with its player, game and opponent, kept even when a reference is missing.
STATS = """
    player_game_stats s
    LEFT JOIN players p ON p.id = s.player_id
    LEFT JOIN games g ON g.id = s.game_id
    LEFT JOIN teams o ON o.id = s.opponent_team_id
"""
STAT_KEY = "s.player_id, s.game_id"
COUNTING_STATS = [
    "minutes", "points", "rebounds", "assists", "field_goals_made", "field_goals_attempted",
    "three_pointers_made", "three_pointers_attempted", "free_throws_made", "free_throws_attempted",
    "offensive_rebounds", "defensive_rebounds", "steals", "blocks", "turnovers", "personal_fouls",
]


def pct_mismatch(pct, made, attempted):
    return (f"s.{pct} IS NOT NULL AND s.{attempted} > 0 "
            f"AND ABS(s.{pct} - s.{made}::float / s.{attempted}) > {PCT_TOLERANCE}")


# (category, severity, check name, scope (FROM clause), failing condition, sample key columns)
# Scope rows are the "rows checked"; rows matching the condition are the failures.
# All SQL here is static: no user input is formatted into queries.
CHECKS = [
    # Duplicates
    ("duplicates", "error", "one stat row per player per game",
     "(SELECT player_id, game_id, COUNT(*) AS n FROM player_game_stats GROUP BY 1, 2) d",
     "d.n > 1", "d.player_id, d.game_id, d.n"),
    ("duplicates", "error", "one stat row per player per game date",
     ("(SELECT s.player_id, g.game_date, COUNT(*) AS n FROM player_game_stats s"
     " JOIN games g ON g.id = s.game_id GROUP BY 1, 2) d"),
     "d.n > 1", "d.player_id, d.game_date, d.n"),
    ("duplicates", "error", "one game per date and team pair (either home/away order)",
     ("(SELECT game_date, LEAST(home_team_id, away_team_id) AS team_a,"
     " GREATEST(home_team_id, away_team_id) AS team_b, COUNT(*) AS n FROM games GROUP BY 1, 2, 3) d"),
     "d.n > 1", "d.game_date, d.team_a, d.team_b, d.n"),
    ("duplicates", "error", "one game per team per date",
     ("(SELECT game_date, team_id, COUNT(*) AS n FROM games"
     " CROSS JOIN LATERAL (VALUES (home_team_id), (away_team_id)) v(team_id) GROUP BY 1, 2) d"),
     "d.n > 1", "d.game_date, d.team_id, d.n"),
    ("duplicates", "warning", "player names map to one player ID among players with stats",
     ("(SELECT LOWER(BTRIM(full_name)) AS name, COUNT(*) AS n FROM players"
     " WHERE id IN (SELECT player_id FROM player_game_stats) GROUP BY 1) d"),
     "d.n > 1", "d.name, d.n"),

    # Missing required fields
    ("missing", "error", "stat row has player_id and game_id", STATS,
     "s.player_id IS NULL OR s.game_id IS NULL", STAT_KEY),
    ("missing", "error", "game has game_date, home_team_id and away_team_id", "games g",
     "g.game_date IS NULL OR g.home_team_id IS NULL OR g.away_team_id IS NULL", "g.id"),
    ("missing", "error", "player has full_name", "players p",
     "p.full_name IS NULL OR BTRIM(p.full_name) = ''", "p.id"),
    ("missing", "error", "stat row has minutes, points, rebounds and assists", STATS,
     "s.minutes IS NULL OR s.points IS NULL OR s.rebounds IS NULL OR s.assists IS NULL", STAT_KEY),
    ("missing", "error", "stat row has opponent_team_id and is_home", STATS,
     "s.opponent_team_id IS NULL OR s.is_home IS NULL", STAT_KEY),
    ("missing", "warning", "stat row has matchup and win_loss", STATS,
     "s.matchup IS NULL OR s.win_loss IS NULL", STAT_KEY),

    # Numeric validity
    ("numeric", "error", "counting stats are not negative", STATS,
     " OR ".join(f"s.{column} < 0" for column in COUNTING_STATS), STAT_KEY),
    ("numeric", "error", f"minutes within 0-{MAX_MINUTES}", STATS, f"s.minutes > {MAX_MINUTES}", STAT_KEY),
    ("numeric", "error", f"points within 0-{MAX_POINTS}", STATS, f"s.points > {MAX_POINTS}", STAT_KEY),
    ("numeric", "error", f"rebounds within 0-{MAX_REBOUNDS}", STATS, f"s.rebounds > {MAX_REBOUNDS}", STAT_KEY),
    ("numeric", "error", f"assists within 0-{MAX_ASSISTS}", STATS, f"s.assists > {MAX_ASSISTS}", STAT_KEY),
    ("numeric", "error", "made shots do not exceed attempts", STATS,
     ("s.field_goals_made > s.field_goals_attempted OR s.three_pointers_made > s.three_pointers_attempted"
     " OR s.free_throws_made > s.free_throws_attempted OR s.three_pointers_made > s.field_goals_made"),
     STAT_KEY),
    ("numeric", "error", "shooting percentages within 0-1", STATS,
     " OR ".join(f"s.{pct} < 0 OR s.{pct} > 1 OR s.{pct} = 'NaN'::float"
                 for pct in ["field_goal_pct", "three_point_pct", "free_throw_pct"]), STAT_KEY),
    ("numeric", "warning", "shooting percentages equal made / attempted", STATS,
     " OR ".join([pct_mismatch("field_goal_pct", "field_goals_made", "field_goals_attempted"),
                  pct_mismatch("three_point_pct", "three_pointers_made", "three_pointers_attempted"),
                  pct_mismatch("free_throw_pct", "free_throws_made", "free_throws_attempted")]),
     STAT_KEY),
    ("numeric", "error", "points equal 2*FGM + 3PM + FTM", STATS,
     "s.points <> 2 * s.field_goals_made + s.three_pointers_made + s.free_throws_made", STAT_KEY),
    ("numeric", "error", "rebounds equal offensive + defensive rebounds", STATS,
     "s.rebounds <> s.offensive_rebounds + s.defensive_rebounds", STAT_KEY),
    # Warning only: minutes are stored as whole numbers, so a sub-minute stint can record a stat.
    ("numeric", "warning", "points, rebounds and assists are zero when minutes are zero", STATS,
     "s.minutes = 0 AND (s.points > 0 OR s.rebounds > 0 OR s.assists > 0)", STAT_KEY),
    ("numeric", "error", "recent_minutes_avg is a non-negative number", STATS,
     "s.recent_minutes_avg < 0 OR s.recent_minutes_avg = 'NaN'::float", STAT_KEY),

    # Relationships
    ("relationships", "error", "stat row's player exists", STATS, "p.id IS NULL", STAT_KEY),
    ("relationships", "error", "stat row's game exists", STATS, "g.id IS NULL", STAT_KEY),
    ("relationships", "error", "stat row's opponent team exists", STATS,
     "s.opponent_team_id IS NOT NULL AND o.id IS NULL", STAT_KEY),
    ("relationships", "error", "opponent and is_home agree with the game's teams", STATS,
     ("g.id IS NOT NULL AND s.is_home IS NOT NULL AND s.opponent_team_id IS NOT NULL"
     " AND s.opponent_team_id <> CASE WHEN s.is_home THEN g.away_team_id ELSE g.home_team_id END"),
     STAT_KEY),
    ("relationships", "error", "matchup's team abbreviation is one of the game's teams", STATS,
     ("s.matchup IS NOT NULL AND g.id IS NOT NULL AND NOT EXISTS ("
     "SELECT 1 FROM teams t WHERE t.abbreviation = split_part(BTRIM(s.matchup), ' ', 1)"
     " AND t.id IN (g.home_team_id, g.away_team_id))"), STAT_KEY),
    ("relationships", "error", "game's home and away teams exist and differ",
     "games g LEFT JOIN teams h ON h.id = g.home_team_id LEFT JOIN teams a ON a.id = g.away_team_id",
     "h.id IS NULL OR a.id IS NULL OR g.home_team_id = g.away_team_id", "g.id"),
    ("relationships", "error", "player's current team exists",
     "players p LEFT JOIN teams t ON t.id = p.team_id", "p.team_id IS NOT NULL AND t.id IS NULL", "p.id"),
    ("relationships", "error", "stat rows are for games on or before today", STATS,
     "g.game_date > CURRENT_DATE", STAT_KEY),
    ("relationships", "warning", "every stored game has at least one stat row",
     "games g", "NOT EXISTS (SELECT 1 FROM player_game_stats s WHERE s.game_id = g.id)", "g.id"),
]

TABLES = ["teams", "players", "games", "player_game_stats"]


def run_check(connection, category, severity, name, scope, condition, key_columns):
    checked, failing = connection.execute(
        f"SELECT COUNT(*), COUNT(*) FILTER (WHERE COALESCE(({condition}), FALSE)) FROM {scope}"
    ).fetchone()
    samples = []
    if failing:
        cursor = connection.execute(
            f"SELECT {key_columns} FROM {scope} WHERE COALESCE(({condition}), FALSE)"
            f" ORDER BY {key_columns} LIMIT {SAMPLE_LIMIT}"
        )
        names = [column.name for column in cursor.description]
        samples = [{n: str(v) for n, v in zip(names, row)} for row in cursor.fetchall()]
    return {
        "category": category, "severity": severity, "check": name,
        "rows_checked": checked, "failing_rows": failing,
        "passed": failing == 0, "samples": samples,
    }


def build_report(connection) -> dict:
    counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    first, last = connection.execute("SELECT MIN(game_date), MAX(game_date) FROM games").fetchone()
    checks = [run_check(connection, *check) for check in CHECKS]
    failed = [c for c in checks if not c["passed"]]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "table_counts": counts,
        "game_date_range": [str(first) if first else None, str(last) if last else None],
        "summary": {
            "checks_run": len(checks),
            "checks_passed": len(checks) - len(failed),
            "errors": sum(c["severity"] == "error" for c in failed),
            "warnings": sum(c["severity"] == "warning" for c in failed),
            "stat_records_checked": counts["player_game_stats"],
            "invalid_stat_records": invalid_stat_record_count(connection),
            "duplicate_groups": sum(c["failing_rows"] for c in checks
                                    if c["category"] == "duplicates" and c["severity"] == "error"),
        },
        "passed": not any(c["severity"] == "error" for c in failed),
        "checks": checks,
    }


def invalid_stat_record_count(connection) -> int:
    """Distinct stat rows failing at least one error check scoped to player_game_stats."""
    conditions = [f"COALESCE(({condition}), FALSE)"
                  for _, severity, _, scope, condition, _ in CHECKS if scope is STATS and severity == "error"]
    return connection.execute(f"SELECT COUNT(*) FROM {STATS} WHERE {' OR '.join(conditions)}").fetchone()[0]


def to_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# NBA Database Data-Quality Report",
        "",
        f"Generated: {report['generated_at']}  ",
        f"Result: **{'PASS' if report['passed'] else 'FAIL'}**  ",
        f"Games stored: {report['game_date_range'][0]} to {report['game_date_range'][1]}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| {table} rows | {count} |" for table, count in report["table_counts"].items()],
        f"| Checks run | {summary['checks_run']} |",
        f"| Checks passed | {summary['checks_passed']} |",
        f"| Failed error checks | {summary['errors']} |",
        f"| Failed warning checks | {summary['warnings']} |",
        f"| Stat records checked | {summary['stat_records_checked']} |",
        f"| Invalid stat records (fail any error check) | {summary['invalid_stat_records']} |",
        f"| Duplicate groups | {summary['duplicate_groups']} |",
        "",
        "## Checks",
        "",
        "| Category | Severity | Check | Rows checked | Failing | Result |",
        "|---|---|---|---|---|---|",
    ]
    for c in report["checks"]:
        result = "pass" if c["passed"] else "**FAIL**" if c["severity"] == "error" else "warn"
        lines.append(f"| {c['category']} | {c['severity']} | {c['check']} | "
                     f"{c['rows_checked']} | {c['failing_rows']} | {result} |")
    failed = [c for c in report["checks"] if not c["passed"]]
    if failed:
        lines += ["", "## Sample failing rows", "", f"Up to {SAMPLE_LIMIT} per check.", ""]
        for c in failed:
            lines.append(f"### {c['check']} ({c['severity']}, {c['failing_rows']} rows)")
            lines += ["", *[f"- `{json.dumps(sample)}`" for sample in c["samples"]], ""]
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Read-only NBA database data-quality report.")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--output", help="also write the report to this file")
    args = parser.parse_args()

    with psycopg.connect(get_database_url()) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        report = build_report(connection)
        connection.rollback()

    text = json.dumps(report, indent=2) + "\n" if args.json else to_markdown(report)
    sys.stdout.write(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run(main))
