from nba_api.stats.endpoints import playergamelog

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

    game_log = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=season,
        season_type_all_star="Regular Season",
    )

    raw_df = game_log.get_data_frames()[0]

    if raw_df.empty:
        return raw_df

    return clean_player_game_log(raw_df)