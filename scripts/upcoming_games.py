"""Return NBA games scheduled in the next 14 days using ESPN.

The script prints JSON to stdout so the Node/Express server can consume it.
ESPN events are adapted to the existing schedule response contract.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.collection.espn import SITE, abbreviation, request_json

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


def schedule_row(event):
    competition = event["competitions"][0]
    status = competition["status"]["type"]
    row = {
        "gameId": f"espn:{event['id']}", "gameDateTimeUTC": event["date"],
        "gameStatus": {"pre": 1, "in": 2, "post": 3}[status["state"]],
        "gameStatusText": status["detail"],
        "gameLabel": event.get("season", {}).get("slug", ""),
    }
    venue = competition.get("venue", {})
    row.update(arenaName=venue.get("fullName", ""),
               arenaCity=venue.get("address", {}).get("city", ""),
               arenaState=venue.get("address", {}).get("state", ""))
    for competitor in competition["competitors"]:
        prefix = competitor["homeAway"] + "Team"
        team = competitor["team"]
        row.update({f"{prefix}_teamCity": team["location"],
                    f"{prefix}_teamName": team["name"],
                    f"{prefix}_teamTricode": abbreviation(team),
                    f"{prefix}_score": competitor.get("score")})
    return row


def fetch_schedule_rows(season: str, start=None, end=None) -> list[dict[str, Any]]:
    # ESPN's NBA scoreboard accepts single dates, not date ranges.
    now = datetime.now(UTC)
    start = start or now - timedelta(days=14)
    end = end or now + timedelta(days=LOOKAHEAD_DAYS)
    first_day = start.astimezone(ZoneInfo("America/New_York")).date()
    last_day = end.astimezone(ZoneInfo("America/New_York")).date()
    days = [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]
    def fetch_day(day):
        return request_json(SITE, "scoreboard", dates=day.strftime("%Y%m%d"), limit=100)["events"]
    with ThreadPoolExecutor(max_workers=6) as executor:
        events = {event["id"]: event for daily in executor.map(fetch_day, days) for event in daily}
    return [schedule_row(event) for event in events.values()
            if season_for_date(datetime.fromisoformat(event["date"])) == season]


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

    # The adapter normally supplies gameDateTimeUTC. This fallback keeps the
    # feature usable if ESPN changes the timestamp shape but leaves the game date.
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
        rows.extend(fetch_schedule_rows(season, start, end))

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
        rows.extend(fetch_schedule_rows(season, now, end))

    games = normalize_upcoming_games(rows, now, LOOKAHEAD_DAYS)
    return {
        "success": True,
        "source": "ESPN",
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
