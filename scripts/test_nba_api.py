from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playergamelog
from scripts.clean_nba_data import clean_player_game_log


def main():
    nba_players = players.get_players()
    nba_teams = teams.get_teams()

    print("Number of players:", len(nba_players))
    print("Number of teams:", len(nba_teams))

    print("\nSample players:")
    for player in nba_players[:5]:
        print(player)

    print("\nSample teams:")
    for team in nba_teams[:5]:
        print(team)

    # Retrieve a real player game log
    curry = players.find_players_by_full_name("Stephen Curry")[0]

    game_log = playergamelog.PlayerGameLog(
        player_id=curry["id"],
        season="2025-26",
        season_type_all_star="Regular Season"
    )

    raw_df = game_log.get_data_frames()[0]

    print("\nRaw columns:")
    print(raw_df.columns.tolist())

    clean_df = clean_player_game_log(raw_df)

    print("\nCleaned columns:")
    print(clean_df.columns.tolist())

    print("\nCleaned sample:")
    print(clean_df.head())

    print("\nCleaned data types:")
    print(clean_df.dtypes)

    # Testing cleaner on NBA API output
    clean_df = clean_player_game_log(raw_df)

    print(clean_df.head())
    print(clean_df.dtypes)


if __name__ == "__main__":
    main()