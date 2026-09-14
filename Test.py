from nba_api.stats.endpoints import playergamelog

try:
    game_log = playergamelog.PlayerGameLog(
        player_id=2544,
        season="2025-26"
    )

    df = game_log.get_data_frames()[0]

    print(
        f"NBA API test successful. "
        f"Retrieved {len(df)} records."
    )

except Exception as e:
    print(f"NBA API test failed: {e}")
    raise   