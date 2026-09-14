from nba_api.stats.static import players, teams


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


if __name__ == "__main__":
    main()