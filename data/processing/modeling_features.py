import pandas as pd


def parse_player_matchup(matchup: str) -> tuple[str, str, bool]:
    """
    Parse an NBA matchup from the player's perspective.

    Returns:
        (
            player's team abbreviation,
            opponent abbreviation,
            is_home
        )

    Examples:
        "GSW vs. LAL" -> ("GSW", "LAL", True)
        "GSW @ POR"   -> ("GSW", "POR", False)
    """

    if " vs. " in matchup:
        team_abbreviation, opponent_abbreviation = matchup.split(" vs. ")

        return (
            team_abbreviation.strip(),
            opponent_abbreviation.strip(),
            True,
        )

    if " @ " in matchup:
        team_abbreviation, opponent_abbreviation = matchup.split(" @ ")

        return (
            team_abbreviation.strip(),
            opponent_abbreviation.strip(),
            False,
        )

    raise ValueError(f"Unrecognized matchup format: {matchup}")


def add_modeling_context(
    game_logs: pd.DataFrame,
    recent_games: int = 5,
) -> pd.DataFrame:
    """
    Add modeling context fields to cleaned NBA player game logs.

    Adds:
        team_abbreviation
        opponent_abbreviation
        is_home
        recent_minutes_avg

    recent_minutes_avg is calculated using only games that occurred
    before the current game to prevent data leakage.
    """

    contextualized = game_logs.copy()

    matchup_context = contextualized["matchup"].apply(
        parse_player_matchup
    )

    contextualized["team_abbreviation"] = matchup_context.apply(
        lambda values: values[0]
    )

    contextualized["opponent_abbreviation"] = matchup_context.apply(
        lambda values: values[1]
    )

    contextualized["is_home"] = matchup_context.apply(
        lambda values: values[2]
    )

    contextualized = contextualized.sort_values(
        by=["player_id", "game_date"]
    ).reset_index(drop=True)

    contextualized["recent_minutes_avg"] = (
        contextualized
        .groupby("player_id")["minutes"]
        .transform(
            lambda minutes: (
                minutes
                .shift(1)
                .rolling(
                    window=recent_games,
                    min_periods=1,
                )
                .mean()
            )
        )
    )

    return contextualized