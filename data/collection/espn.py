"""ESPN retrieval with legacy NBA identities preserved at the source boundary."""

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"
PLAYER_ID_OFFSET = 9_000_000_000
LEGACY = json.loads(Path(__file__).with_name("legacy_nba_ids.json").read_text())
PLAYER_IDS = json.loads(Path(__file__).with_name("espn_player_ids.json").read_text())
ABBREVIATIONS = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}


def request_json(base, path, **params):
    response = requests.get(f"{base}/{path}", params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError(f"Invalid ESPN response for {path}")
    return payload


def normalize_name(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def legacy_player_id(athlete):
    """Use only a unique exact normalized name; never guess between identities."""
    verified = [
        int(key)
        for key, value in PLAYER_IDS.items()
        if value["espn_id"] == str(athlete["id"])
    ]
    if verified:
        return verified[0]
    name = normalize_name(athlete["displayName"])
    matches = [
        int(key)
        for key, value in LEGACY["players"].items()
        if normalize_name(value) == name
    ]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous legacy player mapping: {athlete['displayName']}")
    if matches:
        return matches[0]
    # New ESPN-only athletes have a separate positive ID range understood by the backend.
    return PLAYER_ID_OFFSET + int(athlete["id"])


def abbreviation(team):
    value = team["abbreviation"]
    return ABBREVIATIONS.get(value, value)


@lru_cache(maxsize=1)
def get_teams():
    payload = request_json(SITE, "teams", limit=100)
    result = []
    for item in payload["sports"][0]["leagues"][0]["teams"]:
        team = item["team"]
        matches = [
            old for old in LEGACY["teams"] if old["abbreviation"] == abbreviation(team)
        ]
        if len(matches) != 1:
            raise ValueError(f"Unknown ESPN team mapping: {team['displayName']}")
        result.append({**matches[0], "espn_id": str(team["id"])})
    if len(result) != 30 or len({t["id"] for t in result}) != 30:
        raise ValueError("ESPN must return 30 distinct NBA teams")
    return result


def _roster(team):
    payload = request_json(SITE, f"teams/{team['espn_id']}/roster")
    athletes = payload["athletes"]
    if not athletes:
        raise ValueError(f"Empty ESPN roster for {team['full_name']}")
    return athletes


@lru_cache(maxsize=1)
def get_players():
    result = {}
    nba_teams = get_teams()
    with ThreadPoolExecutor(max_workers=6) as executor:
        for team, roster in zip(nba_teams, executor.map(_roster, nba_teams)):
            for athlete in roster:
                player_id = legacy_player_id(athlete)
                player = {
                    "id": player_id,
                    "espn_id": str(athlete["id"]),
                    "full_name": athlete["displayName"],
                    "first_name": athlete["firstName"],
                    "last_name": athlete["lastName"],
                    "is_active": True,
                    "team_id": team["id"],
                }
                if (
                    player_id in result
                    and result[player_id]["espn_id"] != player["espn_id"]
                ):
                    raise ValueError(
                        f"Conflicting ESPN identity for player {player_id}"
                    )
                result[player_id] = player
    return list(result.values())


def find_player_by_id(player_id):
    return next((p for p in get_players() if p["id"] == int(player_id)), None)


def find_players_by_full_name(name):
    return [p for p in get_players() if name.lower() in p["full_name"].lower()]


def get_active_players():
    return get_players()


def espn_player_id(player_id):
    if int(player_id) >= PLAYER_ID_OFFSET:
        return str(int(player_id) - PLAYER_ID_OFFSET)
    player = PLAYER_IDS.get(str(player_id))
    if player is None:
        raise ValueError(f"No verified ESPN mapping for legacy player {player_id}")
    return player["espn_id"]


def team_game_log(team, season, limit=10):
    payload = request_json(
        SITE,
        f"teams/{team['espn_id']}/schedule",
        season=season_end_year(season),
        seasontype=2,
    )
    events = [
        event
        for event in payload["events"]
        if event["competitions"][0]["status"]["type"]["completed"]
    ]
    rows = []
    for event in sorted(events, key=lambda e: e["date"], reverse=True)[:limit]:
        summary = game_summary(event["id"])
        if summary["header"]["season"]["type"] != 2:
            continue
        competition = summary["header"]["competitions"][0]
        own = next(
            c for c in competition["competitors"] if str(c["id"]) == team["espn_id"]
        )
        opponent = next(c for c in competition["competitors"] if c is not own)
        box = next(
            t
            for t in summary["boxscore"]["teams"]
            if str(t["team"]["id"]) == team["espn_id"]
        )
        stats = {s["name"]: s["displayValue"] for s in box["statistics"]}
        record = next(r["summary"] for r in own["record"] if r["type"] == "total")
        wins, losses = map(int, record.split("-"))
        rows.append(
            {
                "GAME_DATE": game_date(competition["date"]),
                "MATCHUP": f"{team['abbreviation']}{' vs. ' if own['homeAway'] == 'home' else ' @ '}{abbreviation(opponent['team'])}",
                "WL": "W" if own["winner"] else "L",
                "PTS": int(own["score"]),
                "W": wins,
                "L": losses,
                "REB": int(stats["totalRebounds"]),
                "AST": int(stats["assists"]),
            }
        )
    return rows


def season_end_year(season):
    if (
        not re.fullmatch(r"\d{4}-\d{2}", season)
        or int(season[5:]) != (int(season[:4]) + 1) % 100
    ):
        raise ValueError("Season must use YYYY-YY format")
    return int(season[:4]) + 1


def player_events(player_id, season):
    payload = request_json(
        COMMON,
        f"athletes/{espn_player_id(player_id)}/gamelog",
        season=season_end_year(season),
    )
    events = {}
    # The regular-season category excludes preseason, play-in and playoff games.
    for season_type in payload["seasonTypes"]:
        if season_type["displayName"] != f"{season} Regular Season":
            continue
        for category in season_type["categories"]:
            if category["type"] != "event":
                continue
            for event in category["events"]:
                event_id = event["eventId"]
                metadata = payload["events"][event_id]
                events[event_id] = {
                    **metadata,
                    "stats": dict(zip(payload["names"], event["stats"], strict=True)),
                }
    return events


@lru_cache(maxsize=256)
def game_summary(event_id):
    payload = request_json(SITE, "summary", event=event_id)
    if str(payload["header"]["id"]) != str(event_id):
        raise ValueError("ESPN returned a different event")
    return payload


def game_date(value):
    return (
        datetime.fromisoformat(value)
        .astimezone(ZoneInfo("America/New_York"))
        .date()
        .isoformat()
    )


def player_boxscore(summary, athlete_id, player_id):
    header = summary["header"]
    competition = header["competitions"][0]
    if header["season"]["type"] != 2 or not competition["status"]["type"]["completed"]:
        return None
    competitors = competition["competitors"]
    if len(competitors) != 2:
        raise ValueError("Expected two competitors")
    for team in summary["boxscore"]["players"]:
        for group in team["statistics"]:
            for entry in group["athletes"]:
                if str(entry["athlete"]["id"]) != str(athlete_id):
                    continue
                if entry.get("didNotPlay"):
                    return None
                stats = dict(zip(group["labels"], entry["stats"], strict=True))
                own = next(
                    c for c in competitors if str(c["id"]) == str(team["team"]["id"])
                )
                opponent = next(c for c in competitors if c is not own)
                matchup = f"{abbreviation(own['team'])}{' vs. ' if own['homeAway'] == 'home' else ' @ '}{abbreviation(opponent['team'])}"
                minutes = stats["MIN"].split(":")
                if (
                    len(minutes) > 2
                    or float(minutes[0]) < 0
                    or (len(minutes) == 2 and not 0 <= int(minutes[1]) < 60)
                ):
                    raise ValueError(f"Invalid ESPN minutes: {stats['MIN']}")
                row = {
                    "Player_ID": player_id,
                    "Game_ID": f"espn:{header['id']}",
                    "GAME_DATE": game_date(competition["date"]),
                    "MATCHUP": matchup,
                    "WL": "W" if own["winner"] else "L",
                    "MIN": int(
                        float(minutes[0])
                        + (float(minutes[1]) / 60 if len(minutes) == 2 else 0)
                        + 0.5
                    ),
                }
                for source, target in {"FG": "FG", "3PT": "FG3", "FT": "FT"}.items():
                    made, attempted = map(int, stats[source].split("-"))
                    if not 0 <= made <= attempted:
                        raise ValueError(
                            f"Invalid shooting statistics: {stats[source]}"
                        )
                    row[f"{target}M"] = made
                    row[f"{target}A"] = attempted
                    row[f"{target}_PCT"] = (
                        round(made / attempted, 3) if attempted else 0.0
                    )
                for source, target in {
                    "PTS": "PTS",
                    "REB": "REB",
                    "AST": "AST",
                    "OREB": "OREB",
                    "DREB": "DREB",
                    "STL": "STL",
                    "BLK": "BLK",
                    "TO": "TOV",
                    "PF": "PF",
                    "+/-": "PLUS_MINUS",
                }.items():
                    row[target] = int(stats[source])
                    if source != "+/-" and row[target] < 0:
                        raise ValueError(f"Negative ESPN statistic: {source}")
                return row
    raise ValueError(f"ESPN box score missing athlete {athlete_id}")
