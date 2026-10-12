import math

import pandas as pd

FEATURE_COLS = ["pts_season_avg", "pts_last5_avg", "pts_last10_avg"]


def assign_season(game_dates: pd.Series) -> pd.Series:
    """
    Return the NBA season start year for each game date.

    Games from October to December belong to that year's season;
    games from January to September belong to the previous year's.
    """

    return game_dates.dt.year.where(
        game_dates.dt.month >= 10,
        game_dates.dt.year - 1,
    )


def add_points_features(games: pd.DataFrame) -> pd.DataFrame:
    """
    Add season, last-5 and last-10 points averages for each game.

    Every feature is calculated only from the player's earlier games,
    so a player's first game (or first game of a season, for the
    season average) has no value.

    Args:
        games: Player game logs with player_id, game_date and points.

    Returns:
        A sorted copy of games with season and FEATURE_COLS added.
    """

    games = games.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    games["season"] = assign_season(games["game_date"])

    prior_points = games.groupby("player_id")["points"].shift(1)
    prior_season_points = games.groupby(["player_id", "season"])["points"].shift(1)

    games["pts_season_avg"] = prior_season_points.groupby(
        [games["player_id"], games["season"]]
    ).transform(lambda s: s.expanding(min_periods=1).mean())

    for window in (5, 10):
        games[f"pts_last{window}_avg"] = prior_points.groupby(
            games["player_id"]
        ).transform(lambda s, w=window: s.rolling(w, min_periods=1).mean())

    games[FEATURE_COLS] = games[FEATURE_COLS].round(2)

    return games


def time_split(
    games: pd.DataFrame,
    train_fraction: float = 0.8,
) -> pd.DataFrame:
    """
    Label each game as train or test by date.

    The oldest train_fraction of game dates go to train and the rest to
    test, so every train game is played before every test game.

    Raises:
        ValueError: If train_fraction is not between 0 and 1, or there
            are fewer than 2 game dates to split.
    """

    if not 0 < train_fraction < 1:
        raise ValueError(
            f"train_fraction must be between 0 and 1, got {train_fraction}"
        )

    game_dates = sorted(games["game_date"].unique())

    if len(game_dates) < 2:
        raise ValueError("Need at least 2 game dates to split")

    cutoff_index = max(math.floor(len(game_dates) * train_fraction) - 1, 0)
    train_cutoff = game_dates[cutoff_index]

    games = games.copy()
    games["split"] = (games["game_date"] <= train_cutoff).map(
        {True: "train", False: "test"}
    )

    return games
