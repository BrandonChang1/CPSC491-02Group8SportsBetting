import pandas as pd

from data.collection.espn import (
    espn_player_id,
    game_summary,
    player_boxscore,
    player_events,
)
from scripts.clean_nba_data import clean_player_game_log


def fetch_player_game_log(
    player_id: int,
    season: str,
):
    """
    Retrieve and clean an NBA player's historical game log.

    Args:
        player_id: NBA player identifier.
        season: NBA season in YYYY-YY format, for example "2025-26".

    Returns:
        A cleaned pandas DataFrame containing the player's game log.
    """

    athlete_id = espn_player_id(player_id)
    rows = [player_boxscore(game_summary(event_id), athlete_id, player_id)
            for event_id in player_events(player_id, season)]
    raw_df = pd.DataFrame([row for row in rows if row is not None])

    if raw_df.empty:
        return raw_df

    return clean_player_game_log(raw_df)
