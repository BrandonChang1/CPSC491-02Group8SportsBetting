"""Fetch only ESPN game summaries absent from the supplied game-date cache.

Output stays compatible with public/player-search.html. Only regular season,
completed games are considered. This script never writes to PostgreSQL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.collection.espn import (
    espn_player_id,
    game_summary,
    player_boxscore,
    player_events,
)


def main():
    player_id = int(sys.argv[1])
    season = sys.argv[2]
    count = max(0, min(int(sys.argv[3]), 100))
    excluded_dates = set(json.loads(sys.argv[4]))
    newer_than = sys.argv[5] if len(sys.argv) > 5 else ""
    events = player_events(player_id, season)
    # The schedule dates are used only to sort candidate events, never as
    # evidence the game contains a box score.
    ordered = sorted(events.items(), key=lambda pair: pair[1].get("gameDate", pair[1].get("date", "")), reverse=True)
    rows = []
    known_espn_id = espn_player_id(player_id)
    for event_id, event in ordered:
        if len(rows) >= count:
            break
        summary_date = event.get("gameDate", event.get("date", ""))[:10]
        if summary_date in excluded_dates or (newer_than and summary_date <= newer_than):
            continue
        row = player_boxscore(game_summary(event_id), known_espn_id, player_id)
        if row is None or row["GAME_DATE"] in excluded_dates:
            continue
        excluded_dates.add(row["GAME_DATE"])
        rows.append({key: row.get(key) for key in (
            "GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST", "PLUS_MINUS"
        )})
    print(json.dumps({"success": True, "data": rows, "total_events": len(events)}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        print(json.dumps({"success": False, "message": str(exc), "data": []}))
        sys.exit(1)
