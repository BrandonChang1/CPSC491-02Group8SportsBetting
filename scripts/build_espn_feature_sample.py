"""Rebuild the ML research CSV offline from the captured ESPN game logs."""

import json
from pathlib import Path

import pandas as pd

from data.collection.espn import game_date
from data.processing.points_features import add_points_features

DIRECTORY = Path(__file__).resolve().parents[1] / "data/sample/espn_feature_research"
FEATURES = [
    "pts_season_avg", "pts_last5_avg", "pts_last10_avg", "recent_minutes_avg",
    "fga_last5_avg", "fga_last10_avg", "is_home", "days_since_last_game",
    "fg_pct_last5_avg", "fta_last5_avg", "three_pa_last5_avg", "pts_last5_std",
]


def load_source(snapshot):
    rows = []
    teams = {team["espn_team_id"]: team["team_id"] for team in snapshot["nba_teams"]}
    for source in snapshot["sources"]:
        for event in source["events"]:
            stats = dict(zip(source["names"], event["stats"], strict=True))
            meta = event["metadata"]
            # ESPN mixes All-Star exhibitions into the regular-season category.
            if meta["homeTeamId"] not in teams or meta["awayTeamId"] not in teams:
                continue
            if meta["atVs"] not in ("vs", "@"):
                raise ValueError(f"Unknown home/away indicator: {meta['atVs']}")
            home = meta["atVs"] == "vs"
            row = {
                "player_id": source["player_id"], "player_name": source["player_name"],
                "espn_player_id": source["espn_player_id"],
                "game_id": f"espn:{event['eventId']}",
                "game_date": pd.Timestamp(game_date(meta["gameDate"])),
                "season_end_year": source["season_end_year"],
                "espn_team_id": meta["homeTeamId"] if home else meta["awayTeamId"],
                "espn_opponent_team_id": meta["awayTeamId"] if home else meta["homeTeamId"],
                "is_home": int(home), "points": int(stats["points"]),
                "minutes": float(stats["minutes"]),
            }
            for key, made_col, attempted_col in [
                ("fieldGoalsMade-fieldGoalsAttempted", "field_goals_made", "field_goals_attempted"),
                ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "three_pointers_made", "three_pointers_attempted"),
                ("freeThrowsMade-freeThrowsAttempted", "free_throws_made", "free_throws_attempted"),
            ]:
                made, attempted = map(int, stats[key].split("-"))
                if not 0 <= made <= attempted:
                    raise ValueError(f"Invalid shooting stats for {row['game_id']}: {stats[key]}")
                row[made_col], row[attempted_col] = made, attempted
            row["field_goal_pct"] = (
                round(row["field_goals_made"] / row["field_goals_attempted"], 3)
                if row["field_goals_attempted"] else 0.0
            )
            row["team_id"] = teams[row["espn_team_id"]]
            row["opponent_team_id"] = teams[row["espn_opponent_team_id"]]
            if row["points"] < 0 or not 0 <= row["minutes"] < float("inf"):
                raise ValueError(f"Invalid points/minutes for {row['game_id']}")
            if row["points"] != 2 * row["field_goals_made"] + row["three_pointers_made"] + row["free_throws_made"]:
                raise ValueError(f"Inconsistent points for {row['game_id']}")
            rows.append(row)
    games = pd.DataFrame(rows)
    if games.empty or games.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Source must contain distinct player-game records")
    if games.duplicated(["player_id", "game_date"]).any():
        raise ValueError("Multiple appearances on one date need tipoff-time ordering")
    return games


def build_features(games):
    games = add_points_features(games)
    players = games.groupby("player_id")
    games["prior_games_count"] = players.cumcount()
    games["days_since_last_game"] = players["game_date"].diff().dt.days
    for column, feature, window in [
        ("minutes", "recent_minutes_avg", 5),
        ("field_goals_attempted", "fga_last5_avg", 5),
        ("field_goals_attempted", "fga_last10_avg", 10),
        ("field_goal_pct", "fg_pct_last5_avg", 5),
        ("free_throws_attempted", "fta_last5_avg", 5),
        ("three_pointers_attempted", "three_pa_last5_avg", 5),
    ]:
        games[feature] = players[column].transform(
            lambda values, w=window: values.shift(1).rolling(w, min_periods=1).mean()
        )
    games["pts_last5_std"] = players["points"].transform(
        lambda values: values.shift(1).rolling(5, min_periods=1).std(ddof=0)
    )
    games[FEATURES] = games[FEATURES].round(4)
    # A complete later season is held out by date; player histories may cross seasons.
    games["split"] = games["season_end_year"].map({2025: "train", 2026: "test"})
    if games["split"].isna().any():
        raise ValueError("Review the chronological split before adding another season")
    actual = [
        "minutes", "field_goals_made", "field_goals_attempted", "field_goal_pct",
        "three_pointers_made", "three_pointers_attempted", "free_throws_made",
        "free_throws_attempted",
    ]
    games = games.rename(columns={column: f"actual_{column}" for column in actual})
    return games.sort_values(["game_date", "player_id"]).reset_index(drop=True)


def main():
    snapshot = json.loads((DIRECTORY / "source_game_logs.json").read_text())
    games = build_features(load_source(snapshot))
    output = DIRECTORY / "points_training.csv"
    games.to_csv(output, index=False, date_format="%Y-%m-%d", float_format="%.4f")
    print(f"Wrote {len(games)} records to {output}")


if __name__ == "__main__":
    main()
