"""Append missing player-game records and retain each refresh attempt's outcome."""

import argparse
import json
import os

import pandas as pd
import psycopg
import requests
from psycopg.rows import dict_row

from data.collection.espn import season_end_year
from data.collection.nba_game_logs import fetch_player_game_log
from data.ingestion.database_ingestion import (
    canonical_game_id,
    get_database_url,
    get_team_id_map,
    ingest_games,
    ingest_player_game_stats,
    parse_matchup,
    recalculate_recent_minutes_avg,
)
from data.ingestion.monitoring import logger, run


def refresh_player(player_id, season):
    """One scoped, append-only refresh; existing raw history is never upserted."""
    if player_id <= 0:
        raise ValueError("Use a positive internal player ID")
    season_end_year(season)
    with psycopg.connect(get_database_url(), autocommit=True) as connection:
        run_id = connection.execute(
            "INSERT INTO ingestion_refresh_runs (player_id, season) VALUES (%s, %s) RETURNING id",
            (player_id, season),
        ).fetchone()[0]
        source_rows = skipped_rows = 0
        logger.info("refresh_started run_id=%d player_id=%d season=%s", run_id, player_id, season)
        try:
            logs = fetch_player_game_log(player_id, season)
            source_rows = len(logs)
            if logs.empty or not logs["player_id"].eq(player_id).all():
                raise ValueError("Empty source or inconsistent player scope")
            if logs[["game_id", "game_date", "matchup"]].isna().any().any():
                raise ValueError("Missing game identity")
            with connection.transaction():
                # Serialize this player's refreshes, including different seasons' rolling context.
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (player_id,))
                team_ids = get_team_id_map(connection)
                existing = {row[0] for row in connection.execute(
                    "SELECT game_id FROM player_game_stats WHERE player_id = %s", (player_id,),
                ).fetchall()}
                pending = []
                seen = set()
                seen_matchups = set()
                for _, row in logs.iterrows():
                    game_id = canonical_game_id(connection, row, team_ids)
                    identity = (pd.Timestamp(row["game_date"]).date(), *parse_matchup(row["matchup"]))
                    if game_id in seen or identity in seen_matchups:
                        raise ValueError("Duplicate canonical player-game identity in source")
                    seen.add(game_id)
                    seen_matchups.add(identity)
                    if game_id in existing:
                        skipped_rows += 1
                    else:
                        pending.append(row)
                if pending:
                    new_logs = pd.DataFrame(pending)
                    core = new_logs[["minutes", "points", "rebounds", "assists"]].apply(pd.to_numeric, errors="raise")
                    if not ((core >= 0) & (core < float("inf"))).all().all():
                        raise ValueError("Missing, negative or non-finite required stats")
                    dates = pd.to_datetime(new_logs["game_date"], errors="raise").dt.date
                    if (dates > pd.Timestamp.now(tz="America/New_York").date()).any():
                        raise ValueError("Future game record")
                    games = ingest_games(new_logs, connection=connection)
                    if games["failed"]:
                        raise ValueError("Game ingestion failed; rolling back refresh")
                    stats = ingest_player_game_stats(new_logs, connection=connection)
                    if stats["failed"]:
                        raise ValueError("Stat ingestion failed; rolling back refresh")
                    recalculate_recent_minutes_avg(connection=connection, player_id=player_id)
                connection.execute(
                    """UPDATE ingestion_refresh_runs
                       SET status = 'succeeded', finished_at = clock_timestamp(),
                           source_rows = %s, inserted_rows = %s, skipped_rows = %s
                       WHERE id = %s""",
                    (source_rows, len(pending), skipped_rows, run_id),
                )
            logger.info("refresh_succeeded run_id=%d inserted_rows=%d skipped_rows=%d", run_id, len(pending), skipped_rows)
            return 0
        except (requests.RequestException, psycopg.Error, ValueError, KeyError, TypeError) as error:
            # Failed batches have rolled back; retain only the safe exception category.
            logger.error("refresh_failed run_id=%d error_type=%s", run_id, type(error).__name__)
            connection.execute(
                """UPDATE ingestion_refresh_runs SET status = 'failed',
                   finished_at = clock_timestamp(), source_rows = %s, skipped_rows = %s,
                   error_type = %s WHERE id = %s""",
                (source_rows, skipped_rows, type(error).__name__, run_id),
            )
            return 1


DEFAULT_MAX_AGE_HOURS = 48
MAX_AGE_ENV = "DATA_FRESHNESS_MAX_AGE_HOURS"

# One row for the scope (NULL player/season = whole database), even with no attempts.
# freshness: failed/running (latest attempt), never_refreshed, stale or fresh (last success age).
FRESHNESS_QUERY = """
    WITH scoped AS (
        SELECT * FROM ingestion_refresh_runs
        WHERE (%(player_id)s::bigint IS NULL OR player_id = %(player_id)s::bigint)
          AND (%(season)s::text IS NULL OR season = %(season)s::text)
    ),
    latest AS (SELECT * FROM scoped ORDER BY id DESC LIMIT 1),
    success AS (
        SELECT MAX(finished_at) AS last_successful_refresh,
               MAX(finished_at) < CURRENT_TIMESTAMP - %(max_age_hours)s * INTERVAL '1 hour' AS too_old
        FROM scoped WHERE status = 'succeeded'
    )
    SELECT latest.*, success.last_successful_refresh,
           COALESCE(success.too_old, TRUE) AS is_stale,
           CASE WHEN latest.status IN ('failed', 'running') THEN latest.status
                WHEN success.last_successful_refresh IS NULL THEN 'never_refreshed'
                WHEN success.too_old THEN 'stale'
                ELSE 'fresh' END AS freshness,
           %(max_age_hours)s::float AS max_age_hours
    FROM success LEFT JOIN latest ON TRUE
"""


def max_age_hours(value=None):
    """Freshness threshold in hours: the argument, else $DATA_FRESHNESS_MAX_AGE_HOURS, else 48."""
    raw = value if value is not None else os.getenv(MAX_AGE_ENV, DEFAULT_MAX_AGE_HOURS)
    hours = float(raw)
    if not 0 < hours < float("inf"):
        raise ValueError(f"{MAX_AGE_ENV} must be a positive number of hours")
    return hours


def _freshness(player_id, season, hours):
    with (
        psycopg.connect(get_database_url()) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        connection.execute("SET TRANSACTION READ ONLY")
        cursor.execute(FRESHNESS_QUERY,
                       {"player_id": player_id, "season": season, "max_age_hours": max_age_hours(hours)})
        return cursor.fetchone()


def get_refresh_status(player_id, season, max_age=None):
    """Return latest attempt, last success and freshness for this exact scope, or None if never attempted."""
    if player_id <= 0:
        raise ValueError("Use a positive internal player ID")
    season_end_year(season)
    status = _freshness(player_id, season, max_age)
    return status if status["id"] is not None else None


def get_database_freshness(max_age=None):
    """Return latest attempt, last success and freshness across every player and season.

    Always returns a dict; freshness is 'never_refreshed' when no attempt has been recorded.
    """
    return _freshness(None, None, max_age)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--season", help="NBA season as YYYY-YY")
    parser.add_argument("--status", action="store_true",
                        help="Read freshness without fetching or writing; omit player and season for the whole database")
    parser.add_argument("--max-age-hours", type=float,
                        help=f"Stale threshold (default ${MAX_AGE_ENV} or {DEFAULT_MAX_AGE_HOURS})")
    args = parser.parse_args()
    scoped = args.player_id is not None, args.season is not None
    if scoped != (True, True) and (not args.status or any(scoped)):
        parser.error("--player-id and --season are required together (both may be omitted only with --status)")
    if args.status:
        status = (get_refresh_status(args.player_id, args.season, args.max_age_hours) if any(scoped)
                  else get_database_freshness(args.max_age_hours))
        print(json.dumps(status, default=str))
        return 0 if status and status["freshness"] == "fresh" else 1
    return refresh_player(args.player_id, args.season)


if __name__ == "__main__":
    raise SystemExit(run(main))
