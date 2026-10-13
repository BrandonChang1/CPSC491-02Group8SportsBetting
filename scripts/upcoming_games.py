"""Return NBA games scheduled in the next 14 days using nba_api.

The script prints JSON to stdout so the Node/Express server can consume it.
It intentionally avoids pandas; nba_api's dictionary interface is sufficient for
this feature and keeps the schedule endpoint independent of DataFrame support.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

LOOKAHEAD_DAYS = 14


def season_for_date(moment: datetime) -> str:
    """Return the NBA season string that contains *moment* (for example 2026-27)."""
    year = moment.year if moment.month >= 7 else moment.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def seasons_for_window(start: datetime, end: datetime) -> list[str]:
    """Return each season that could intersect the requested date window."""
    seasons = [season_for_date(start)]
    ending_season = season_for_date(end)
    if ending_season != seasons[0]:
        seasons.append(ending_season)
    return seasons


def _rows_from_dataset(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    headers = dataset.get("headers", [])
    rows = dataset.get("data", [])
    return [dict(zip(headers, row)) for row in rows]


def fetch_schedule_rows(season: str) -> list[dict[str, Any]]:
    """Fetch one NBA season schedule through nba_api's ScheduleLeagueV2 endpoint."""
    # Import here so pure filtering/unit tests do not need a working network call.
    from nba_api.stats.endpoints import scheduleleaguev2

    schedule = scheduleleaguev2.ScheduleLeagueV2(
        league_id="00",
        season=season,
        timeout=30,
    )
    return _rows_from_dataset(schedule.season_games.get_dict())


def _parse_game_time(row: dict[str, Any]) -> datetime | None:
    """Parse the best available scheduled timestamp and return an aware UTC datetime."""
    utc_value = row.get("gameDateTimeUTC")
    if utc_value:
        value = str(utc_value).strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass

    # ScheduleLeagueV2 normally includes gameDateTimeUTC. This fallback keeps the
    # feature usable if NBA changes the timestamp shape but leaves the game date.
    date_value = row.get("gameDate") or row.get("gameDateUTC")
    time_value = row.get("gameTimeUTC") or "00:00:00"
    if not date_value:
        return None

    date_text = str(date_value).strip().split("T", 1)[0]
    time_text = str(time_value).strip().replace("Z", "")
    candidates = [
        f"{date_text}T{time_text}",
        date_text,
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _team_name(row: dict[str, Any], prefix: str) -> str:
    city = str(row.get(f"{prefix}_teamCity") or "").strip()
    name = str(row.get(f"{prefix}_teamName") or "").strip()
    full_name = " ".join(part for part in (city, name) if part)
    return full_name or str(row.get(f"{prefix}_teamTricode") or "Unknown")


def normalize_upcoming_games(
    rows: Iterable[dict[str, Any]],
    now: datetime,
    days: int = LOOKAHEAD_DAYS,
) -> list[dict[str, Any]]:
    """Filter schedule rows to games after *now* and within the next *days* days."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    end = now + timedelta(days=days)
    games: list[dict[str, Any]] = []

    for row in rows:
        # NBA schedule status 1 means the game has not started.
        try:
            status = int(row.get("gameStatus", 0))
        except (TypeError, ValueError):
            status = 0
        if status != 1:
            continue

        tipoff = _parse_game_time(row)
        if tipoff is None or tipoff <= now or tipoff > end:
            continue

        games.append(
            {
                "gameId": str(row.get("gameId") or ""),
                "tipoffUtc": tipoff.isoformat().replace("+00:00", "Z"),
                "status": str(row.get("gameStatusText") or "Scheduled"),
                "gameLabel": str(row.get("gameLabel") or ""),
                "awayTeam": {
                    "name": _team_name(row, "awayTeam"),
                    "tricode": str(row.get("awayTeam_teamTricode") or ""),
                },
                "homeTeam": {
                    "name": _team_name(row, "homeTeam"),
                    "tricode": str(row.get("homeTeam_teamTricode") or ""),
                },
                "arena": {
                    "name": str(row.get("arenaName") or ""),
                    "city": str(row.get("arenaCity") or ""),
                    "state": str(row.get("arenaState") or ""),
                },
            }
        )

    games.sort(key=lambda game: game["tipoffUtc"])
    return games



def _score(row: dict[str, Any], prefix: str) -> int | None:
    value = row.get(f"{prefix}_score")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def lookup_games(game_ids: Iterable[str], now: datetime | None = None) -> dict[str, Any]:
    """Return status, score, and winner information for specific game IDs."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    requested = {str(game_id) for game_id in game_ids if str(game_id)}
    if not requested:
        return {"success": True, "games": []}

    start = now - timedelta(days=14)
    end = now + timedelta(days=14)
    rows: list[dict[str, Any]] = []
    for season in seasons_for_window(start, end):
        rows.extend(fetch_schedule_rows(season))

    games: list[dict[str, Any]] = []
    for row in rows:
        game_id = str(row.get("gameId") or "")
        if game_id not in requested:
            continue

        try:
            status_code = int(row.get("gameStatus", 0))
        except (TypeError, ValueError):
            status_code = 0

        away_score = _score(row, "awayTeam")
        home_score = _score(row, "homeTeam")
        away_name = _team_name(row, "awayTeam")
        home_name = _team_name(row, "homeTeam")
        winner = None
        if status_code == 3 and away_score is not None and home_score is not None:
            if away_score > home_score:
                winner = away_name
            elif home_score > away_score:
                winner = home_name

        games.append(
            {
                "gameId": game_id,
                "statusCode": status_code,
                "status": str(row.get("gameStatusText") or ""),
                "awayTeam": {"name": away_name},
                "homeTeam": {"name": home_name},
                "awayScore": away_score,
                "homeScore": home_score,
                "winner": winner,
            }
        )

    return {"success": True, "games": games}


def get_upcoming_games(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    end = now + timedelta(days=LOOKAHEAD_DAYS)
    rows: list[dict[str, Any]] = []
    for season in seasons_for_window(now, end):
        rows.extend(fetch_schedule_rows(season))

    games = normalize_upcoming_games(rows, now, LOOKAHEAD_DAYS)
    return {
        "success": True,
        "source": "nba_api ScheduleLeagueV2",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "windowEndsAt": end.isoformat().replace("+00:00", "Z"),
        "count": len(games),
        "games": games,
    }


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "lookup":
            print(json.dumps(lookup_games(sys.argv[2:])))
        else:
            print(json.dumps(get_upcoming_games()))
    except Exception as exc:  # noqa: BLE001 Return machine-readable failure for Express.
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"Unable to retrieve NBA schedule: {exc}",
                    "games": [],
                }
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
