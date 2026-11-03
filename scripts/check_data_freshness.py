"""Check a player's expected completed game without changing stored data."""

import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg

from data.ingestion.database_ingestion import get_database_url
from data.ingestion.monitoring import logger, run

MAX_DELAY_DAYS = 2


def check_freshness(connection, player_id, expected_game_date, as_of_date):
    if player_id <= 0 or expected_game_date > as_of_date:
        raise ValueError("Use a positive player ID and a completed game date")
    latest, expected_count = connection.execute(
        """
        SELECT MAX(g.game_date), COUNT(*) FILTER (WHERE g.game_date = %s)
        FROM player_game_stats s JOIN games g ON g.id = s.game_id
        WHERE s.player_id = %s
        """,
        (expected_game_date, player_id),
    ).fetchone()
    if latest is not None and latest > as_of_date:
        logger.error("freshness_anomaly player_id=%d reason=future_record latest=%s", player_id, latest)
        return 1
    if expected_count > 1:
        logger.error("freshness_anomaly player_id=%d reason=multiple_appearances expected_date=%s", player_id, expected_game_date)
        return 1
    if expected_count == 1:
        logger.info("freshness_ok player_id=%d expected_date=%s latest=%s", player_id, expected_game_date, latest)
        return 0
    delay = (as_of_date - expected_game_date).days
    if delay > MAX_DELAY_DAYS:
        logger.error(
            "freshness_anomaly player_id=%d reason=missing_expected_game expected_date=%s latest=%s delay_days=%d threshold_days=%d",
            player_id, expected_game_date, latest, delay, MAX_DELAY_DAYS,
        )
        return 1
    logger.warning(
        "refresh_pending player_id=%d expected_date=%s latest=%s delay_days=%d threshold_days=%d",
        player_id, expected_game_date, latest, delay, MAX_DELAY_DAYS,
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument("--expected-game-date", type=date.fromisoformat, required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat,
                        default=datetime.now(ZoneInfo("America/New_York")).date())
    args = parser.parse_args()
    with psycopg.connect(get_database_url()) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        return check_freshness(connection, args.player_id, args.expected_game_date, args.as_of_date)


if __name__ == "__main__":
    raise SystemExit(run(main))
