"""Fallback NBA team W/L records, returned as JSON for the Express API.

Only completed regular-season team games strictly before today are used.
Includes previous season when the current season has fewer than ten results.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

TEAM_ABBREVIATIONS = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
}


def seasons_for_today(now):
    year = now.year if now.month >= 7 else now.year - 1
    return [f"{year}-{str(year + 1)[-2:]}", f"{year - 1}-{str(year)[-2:]}"]


def collect_recent_records(season_rows, today, limit=10):
    """Deduplicate team-game results and keep each team's newest games."""
    per_team = {}
    seen = set()
    for row in season_rows:
        team = str(row.get("TEAM_ABBREVIATION") or "").upper()
        game_id = str(row.get("GAME_ID") or "")
        wl = row.get("WL")
        raw_date = str(row.get("GAME_DATE") or "")[:10]
        if team not in TEAM_ABBREVIATIONS or not game_id or wl not in ("W", "L"):
            continue
        try:
            game_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if game_date >= today or (team, game_id) in seen:
            continue
        seen.add((team, game_id))
        per_team.setdefault(team, []).append((game_date, game_id, wl))
    result = {}
    for team, games in per_team.items():
        latest = sorted(games, reverse=True)[:limit]
        result[team] = {"games": len(latest), "wins": sum(wl == "W" for _, _, wl in latest)}
    return result


def fetch_season_rows(season):
    from nba_api.stats.endpoints import leaguegamefinder

    finder = leaguegamefinder.LeagueGameFinder(
        league_id_nullable="00",
        season_nullable=season,
        season_type_nullable="Regular Season",
        timeout=30,
    )
    return finder.get_normalized_dict().get("LeagueGameFinderResults", [])


def main():
    now = datetime.now(UTC)
    all_rows = []
    errors = []
    for season in seasons_for_today(now):
        try:
            all_rows.extend(fetch_season_rows(season))
        except Exception as error:  # noqa: BLE001 - External API failures must not discard other seasons.
            errors.append(f"{season}: {error}")
    if not all_rows:
        print(json.dumps({"success": False, "message": "NBA history API unavailable", "records": {}, "errors": errors}))
        return 1
    print(json.dumps({"success": True, "records": collect_recent_records(all_rows, now.date()), "seasons": seasons_for_today(now), "partial": bool(errors)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
