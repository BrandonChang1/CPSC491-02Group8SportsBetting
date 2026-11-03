"""Append missing player-game records and retain each refresh attempt's outcome."""

import argparse
import json

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


def get_refresh_status(player_id, season):
    """Return latest attempt and last success for this exact scope, or None."""
    if player_id <= 0:
        raise ValueError("Use a positive internal player ID")
    season_end_year(season)
    with (
        psycopg.connect(get_database_url()) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        connection.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT r.*, success.last_successful_refresh,
                      (success.last_successful_refresh IS NULL OR
                       success.last_successful_refresh < CURRENT_TIMESTAMP - INTERVAL '48 hours') AS is_stale
               FROM ingestion_refresh_runs r
               CROSS JOIN LATERAL (
                   SELECT MAX(finished_at) AS last_successful_refresh
                   FROM ingestion_refresh_runs
                   WHERE player_id = r.player_id AND season = r.season AND status = 'succeeded'
               ) success
               WHERE r.player_id = %s AND r.season = %s ORDER BY r.id DESC LIMIT 1""",
            (player_id, season),
        )
        return cursor.fetchone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument("--season", required=True, help="NBA season as YYYY-YY")
    parser.add_argument("--status", action="store_true", help="Read status without fetching or writing")
    args = parser.parse_args()
    if args.status:
        status = get_refresh_status(args.player_id, args.season)
        print(json.dumps(status, default=str))
        return 0 if status and status["status"] == "succeeded" and not status["is_stale"] else 1
    return refresh_player(args.player_id, args.season)


if __name__ == "__main__":
    raise SystemExit(run(main))
