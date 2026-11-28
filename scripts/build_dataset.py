"""Build data/NBA_player_stats.csv from ESPN regular-season box scores.

Every completed regular-season game for SEASONS is fetched once from ESPN and
cached (gzipped JSON) under data/raw/, so reruns make no network calls. Features
are computed by data.processing.full_features from prior games only.

Usage:
    python -m scripts.build_dataset                # fetch what is missing, then build
    python -m scripts.build_dataset --fetch-only   # only fill the cache
    python -m scripts.build_dataset --offline      # build from cache, never call ESPN
"""

import argparse
import gzip
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.collection.espn import (
    LEGACY,
    PLAYER_ID_OFFSET,
    PLAYER_IDS,
    SITE,
    game_date,
    get_teams,
    normalize_name,
    season_end_year,
)

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_CSV = DATA_DIR / "NBA_player_stats.csv"
ID_MAP_CSV = DATA_DIR / "player_id_map.csv"
FEATURES_MD = DATA_DIR / "FEATURES.md"
EXPECTED_ROWS_PER_SEASON = (25_000, 27_000)
RETRIES = 5
TIMEOUT = 30
NAME_SUFFIXES = re.compile(r"(jr|sr|ii|iii|iv|v)$")
SKIPPED_NO_ID = []  # (game_id, team, short name) of box-score entries without an ESPN athlete id


class FetchError(RuntimeError):
    """ESPN stayed unreachable after every retry."""


class OfflineCacheMiss(RuntimeError):
    """--offline was given but a response is not cached."""


class RateLimiter:
    """Space request starts at least `interval` seconds apart across threads."""

    def __init__(self, interval):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_start)
            self.next_start = start + self.interval
        time.sleep(max(0.0, start - now))


class Fetcher:
    """GET with a disk cache, a global rate limit and exponential backoff."""

    def __init__(self, raw_dir=RAW_DIR, delay=1.0, refresh=False, offline=False):
        self.raw_dir = Path(raw_dir)
        self.limiter = RateLimiter(delay)
        self.refresh = refresh
        self.offline = offline
        self.network_calls = 0
        self.count_lock = threading.Lock()

    def cache_path(self, kind, key):
        return self.raw_dir / kind / f"{key}.json.gz"

    def get(self, kind, key, url, params=None, trim=None, allow_404=False):
        path = self.cache_path(kind, key)
        if path.exists() and not self.refresh:
            with gzip.open(path, "rt") as handle:
                return json.load(handle)
        if self.offline:
            raise OfflineCacheMiss(f"Not cached: {path}")

        payload = self._request(url, params, allow_404)
        if trim is not None and "_status" not in payload:
            payload = trim(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as handle:
            json.dump(payload, handle)
        tmp.replace(path)
        return payload

    def _request(self, url, params, allow_404):
        last_error = None
        for attempt in range(RETRIES):
            self.limiter.wait()
            with self.count_lock:
                self.network_calls += 1
            try:
                response = requests.get(url, params=params, timeout=TIMEOUT)
                if response.status_code == 404 and allow_404:
                    return {"_status": 404}
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                return response.json()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < RETRIES - 1:
                    time.sleep(2 ** (attempt + 1))
        raise FetchError(f"ESPN unreachable after {RETRIES} tries: {url} {params} ({last_error})")


# --------------------------------------------------------------------------- teams


def load_teams(fetcher):
    """ESPN team id -> NBA team dict (id, abbreviation, full_name), cached on disk."""

    path = fetcher.raw_dir / "teams.json"
    if path.exists() and not fetcher.refresh:
        teams = json.loads(path.read_text())
    else:
        if fetcher.offline:
            raise OfflineCacheMiss(f"Not cached: {path}")
        teams = get_teams()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(teams, indent=1))
    return {str(team["espn_id"]): team for team in teams}


# ------------------------------------------------------------------------ schedule


def season_event_ids(fetcher, teams, season):
    """Completed regular-season event ids for a season, excluding NBA Cup finals."""

    end_year = season_end_year(season)
    events = {}
    for espn_team_id in sorted(teams, key=int):
        payload = fetcher.get(
            "schedule",
            f"{end_year}_{espn_team_id}",
            f"{SITE}/teams/{espn_team_id}/schedule",
            {"season": end_year, "seasontype": 2},
        )
        for event in payload.get("events", []):
            competition = event["competitions"][0]
            if not competition["status"]["type"]["completed"]:
                continue
            if event.get("seasonType", {}).get("type", 2) != 2:
                continue
            # The NBA Cup championship is listed with regular-season games but
            # does not count toward regular-season statistics.
            if competition.get("type", {}).get("abbreviation") == "CC":
                continue
            events[str(event["id"])] = event["date"]
    return events


# ------------------------------------------------------------------------- summary


def trim_summary(payload):
    return {key: payload[key] for key in ("header", "boxscore", "injuries") if key in payload}


def fetch_summary(fetcher, event_id):
    payload = fetcher.get(
        "summary", event_id, f"{SITE}/summary", {"event": event_id}, trim=trim_summary
    )
    if str(payload["header"]["id"]) != str(event_id):
        raise ValueError(f"ESPN returned a different event for {event_id}")
    return payload


def overtime_periods(status):
    """Number of overtimes from a status detail such as 'Final', 'Final/OT', 'Final/2OT'."""

    period = status.get("period")
    if isinstance(period, int) and period >= 4:
        return period - 4
    detail = status.get("type", {}).get("detail", "")
    match = re.search(r"/(\d*)OT", detail)
    if not match:
        return 0
    return int(match.group(1) or 1)


def made_attempted(value):
    made, attempted = (int(part) for part in value.split("-"))
    if not 0 <= made <= attempted:
        raise ValueError(f"Invalid shooting split: {value}")
    return made, attempted


def parse_minutes(value):
    if value in (None, "", "--"):
        return 0.0
    parts = str(value).split(":")
    return float(parts[0]) + (float(parts[1]) / 60 if len(parts) == 2 else 0.0)


def parse_summary(summary, teams, season):
    """Return (player_rows, team_rows) for one ESPN game summary."""

    header = summary["header"]
    competition = header["competitions"][0]
    event_id = str(header["id"])
    game_id = f"espn:{event_id}"
    date = game_date(competition["date"])
    ot = overtime_periods(competition["status"])
    competitors = {str(c["id"]): c for c in competition["competitors"]}
    if len(competitors) != 2:
        raise ValueError(f"Expected two competitors in {event_id}")

    player_rows = []
    for team_block in summary["boxscore"].get("players", []):
        espn_team_id = str(team_block["team"]["id"])
        own = competitors[espn_team_id]
        opponent_espn_id = next(key for key in competitors if key != espn_team_id)
        for group in team_block["statistics"]:
            labels = group["labels"]
            for entry in group["athletes"]:
                if entry.get("didNotPlay") or not entry.get("stats"):
                    continue
                # "--" minutes with all-zero stats is ESPN's placeholder for a listed
                # player who never entered; a real scoreless cameo shows "0".
                if dict(zip(labels, entry["stats"])).get("MIN") in ("--", ""):
                    continue
                athlete = entry.get("athlete") or {}
                if "id" not in athlete:
                    # ESPN occasionally lists a player with no athlete id; the row
                    # cannot be tied to a player, so it is skipped and reported.
                    SKIPPED_NO_ID.append((game_id, team_block["team"].get("abbreviation"), athlete.get("shortName")))
                    continue
                stats = dict(zip(labels, entry["stats"], strict=True))
                fgm, fga = made_attempted(stats["FG"])
                fg3m, fg3a = made_attempted(stats["3PT"])
                ftm, fta = made_attempted(stats["FT"])
                player_rows.append(
                    {
                        "espn_player_id": str(athlete["id"]),
                        "player_name": athlete.get("displayName", ""),
                        "box_position": (athlete.get("position") or {}).get("abbreviation"),
                        "game_id": game_id,
                        "game_date": date,
                        "season": int(season[:4]),
                        "espn_team_id": espn_team_id,
                        "espn_opponent_id": opponent_espn_id,
                        "is_home": own["homeAway"] == "home",
                        "starter": bool(entry.get("starter")),
                        "minutes": parse_minutes(stats["MIN"]),
                        "points": int(stats["PTS"]),
                        "field_goals_made": fgm,
                        "field_goals_attempted": fga,
                        "three_pointers_made": fg3m,
                        "three_pointers_attempted": fg3a,
                        "free_throws_made": ftm,
                        "free_throws_attempted": fta,
                        "offensive_rebounds": int(stats["OREB"]),
                        "defensive_rebounds": int(stats["DREB"]),
                        "rebounds": int(stats["REB"]),
                        "assists": int(stats["AST"]),
                        "steals": int(stats["STL"]),
                        "blocks": int(stats["BLK"]),
                        "turnovers": int(stats["TO"]),
                        "personal_fouls": int(stats["PF"]),
                        "plus_minus": int(stats["+/-"]),
                    }
                )

    team_rows = []
    for team_block in summary["boxscore"]["teams"]:
        espn_team_id = str(team_block["team"]["id"])
        own = competitors[espn_team_id]
        stats = {s["name"]: s["displayValue"] for s in team_block["statistics"]}
        fgm, fga = made_attempted(stats["fieldGoalsMade-fieldGoalsAttempted"])
        fg3m, fg3a = made_attempted(
            stats["threePointFieldGoalsMade-threePointFieldGoalsAttempted"]
        )
        ftm, fta = made_attempted(stats["freeThrowsMade-freeThrowsAttempted"])
        turnovers = stats.get("totalTurnovers", stats.get("turnovers"))
        team_rows.append(
            {
                "game_id": game_id,
                "game_date": date,
                "season": int(season[:4]),
                "espn_team_id": espn_team_id,
                "is_home": own["homeAway"] == "home",
                "points": int(own["score"]),
                "field_goals_attempted": fga,
                "three_pointers_attempted": fg3a,
                "free_throws_attempted": fta,
                "offensive_rebounds": int(stats["offensiveRebounds"]),
                "turnovers": int(turnovers),
                "overtimes": ot,
            }
        )

    for row in player_rows:
        row["team_id"] = teams[row["espn_team_id"]]["id"]
        row["team_abbreviation"] = teams[row["espn_team_id"]]["abbreviation"]
        row["opponent_team_id"] = teams[row["espn_opponent_id"]]["id"]
        row["opponent_abbreviation"] = teams[row["espn_opponent_id"]]["abbreviation"]
    for row in team_rows:
        row["team_id"] = teams[row["espn_team_id"]]["id"]
    return player_rows, team_rows


# ------------------------------------------------------------------------- athletes


def trim_athlete(payload):
    return {
        key: payload.get(key)
        for key in ("id", "displayName", "dateOfBirth", "height", "debutYear", "experience")
    } | {"position": (payload.get("position") or {}).get("abbreviation")}


def fetch_athlete(fetcher, espn_id, end_year):
    return fetcher.get(
        "athlete",
        espn_id,
        f"{CORE}/seasons/{end_year}/athletes/{espn_id}",
        trim=trim_athlete,
        allow_404=True,
    )


# -------------------------------------------------------------------------- id map


def strip_suffix(normalized):
    return NAME_SUFFIXES.sub("", normalized)


def build_id_map(players, bios=None):
    """Map each ESPN athlete to the app's player_id, never guessing between names.

    Order: verified espn_player_ids.json, then a unique normalized-name match in
    legacy_nba_ids.json, then the same with suffixes (Jr., III, ...) stripped.
    Anything else keeps the app's ESPN-only id (PLAYER_ID_OFFSET + espn id).
    """

    verified = {value["espn_id"]: int(key) for key, value in PLAYER_IDS.items()}
    by_name, by_stripped = {}, {}
    for key, name in LEGACY["players"].items():
        normalized = normalize_name(name)
        by_name.setdefault(normalized, []).append(int(key))
        by_stripped.setdefault(strip_suffix(normalized), []).append(int(key))

    summary = (
        players.sort_values("game_date")
        .groupby("espn_player_id")
        .agg(
            player_name=("player_name", "last"),
            teams=("team_abbreviation", lambda s: "|".join(dict.fromkeys(s))),
            seasons=("season", lambda s: "|".join(str(v) for v in sorted(set(s)))),
        )
        .reset_index()
    )

    rows = []
    for record in summary.itertuples(index=False):
        espn_id = record.espn_player_id
        normalized = normalize_name(record.player_name)
        nba_id, method = None, "unmatched"
        if espn_id in verified:
            nba_id, method = verified[espn_id], "verified"
        elif len(by_name.get(normalized, [])) == 1:
            nba_id, method = by_name[normalized][0], "name"
        elif normalized not in by_name and len(by_stripped.get(strip_suffix(normalized), [])) == 1:
            nba_id, method = by_stripped[strip_suffix(normalized)][0], "suffix_stripped"
        elif len(by_name.get(normalized, [])) > 1:
            method = "ambiguous_name"
        rows.append(
            {
                "player_id": nba_id if nba_id is not None else PLAYER_ID_OFFSET + int(espn_id),
                "nba_player_id": nba_id,
                "espn_player_id": espn_id,
                "player_name": record.player_name,
                "match_method": method,
                "teams": record.teams,
                "seasons": record.seasons,
            }
        )
    id_map = pd.DataFrame(rows)
    id_map["nba_player_id"] = id_map["nba_player_id"].astype("Int64")

    # ESPN sometimes keeps two athlete records for one person (e.g. Trevon Scott).
    # Several ESPN ids may share an NBA id only when their bios agree on birth date
    # and height; any other clash is a bad match and stops the build.
    matched = id_map[id_map["nba_player_id"].notna()]
    clashes = matched[matched["nba_player_id"].duplicated(keep=False)]
    if not clashes.empty:
        if bios is None:
            raise ValueError(f"Two ESPN athletes mapped to one NBA id:\n{clashes}")
        bio = clashes.merge(bios, on="espn_player_id", how="left")
        same_person = bio.groupby("nba_player_id").agg(
            dob=("date_of_birth", lambda s: s.notna().all() and s.nunique() == 1),
            height=("height_in", lambda s: s.notna().all() and s.nunique() == 1),
        )
        bad = same_person[~(same_person["dob"] & same_person["height"])]
        if not bad.empty:
            raise ValueError(f"Two ESPN athletes mapped to one NBA id:\n{bio}")
        id_map.loc[clashes.index, "match_method"] += "+duplicate_espn_record"
    return id_map


# ---------------------------------------------------------------------------- main


def fetch_all(fetcher, seasons, workers):
    teams = load_teams(fetcher)
    player_rows, team_rows = [], []
    for season in seasons:
        events = season_event_ids(fetcher, teams, season)
        print(f"{season}: {len(events)} completed regular-season games", flush=True)
        done = 0

        def one(event_id, season=season):
            return parse_summary(fetch_summary(fetcher, event_id), teams, season)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for players, team in pool.map(one, sorted(events)):
                player_rows.extend(players)
                team_rows.extend(team)
                done += 1
                if done % 200 == 0:
                    print(f"  {season}: {done}/{len(events)} games", flush=True)

    players = pd.DataFrame(player_rows)
    team_games = pd.DataFrame(team_rows)
    if SKIPPED_NO_ID:
        print(f"Skipped {len(SKIPPED_NO_ID)} played box-score entries with no ESPN athlete id: {SKIPPED_NO_ID}")

    last_season = players.groupby("espn_player_id")["season"].max()
    athlete_ids = sorted(last_season.index, key=int)
    print(f"Athlete bios: {len(athlete_ids)}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bios = list(
            pool.map(lambda a: fetch_athlete(fetcher, a, int(last_season[a]) + 1), athlete_ids)
        )
    bio_frame = pd.DataFrame(
        [
            {
                "espn_player_id": athlete_id,
                "date_of_birth": bio.get("dateOfBirth"),
                "height_in": bio.get("height"),
                "debut_year": bio.get("debutYear"),
                "bio_position": bio.get("position"),
            }
            for athlete_id, bio in zip(athlete_ids, bios)
        ]
    )
    return players, team_games, bio_frame


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seasons", nargs="+", default=SEASONS)
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between request starts")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--refresh", action="store_true", help="ignore the cache")
    parser.add_argument("--offline", action="store_true", help="use only cached responses")
    parser.add_argument("--fetch-only", action="store_true")
    args = parser.parse_args(argv)

    fetcher = Fetcher(delay=args.delay, refresh=args.refresh, offline=args.offline)
    started = time.time()
    try:
        players, team_games, bios = fetch_all(fetcher, args.seasons, args.workers)
    except (FetchError, OfflineCacheMiss) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Fetched {len(players)} player rows, {len(team_games)} team rows "
        f"({fetcher.network_calls} network calls, {time.time() - started:.0f}s)",
        flush=True,
    )
    if args.fetch_only:
        return 0

    from data.processing import full_features

    id_map = build_id_map(players, bios)
    dataset = full_features.build_features(players, team_games, bios, id_map)
    full_features.validate(dataset, EXPECTED_ROWS_PER_SEASON)

    dataset.to_csv(OUTPUT_CSV, index=False)
    id_map.to_csv(ID_MAP_CSV, index=False)
    FEATURES_MD.write_text(full_features.features_markdown(dataset))
    print(f"Wrote {OUTPUT_CSV} ({len(dataset)} rows, {dataset.shape[1]} columns)")
    print(f"Wrote {ID_MAP_CSV} and {FEATURES_MD}")
    print(full_features.report(dataset, id_map))
    return 0


if __name__ == "__main__":
    sys.exit(main())
