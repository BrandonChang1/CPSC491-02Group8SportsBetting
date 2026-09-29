# NBA ML Data Dictionary

## Source
nba_api PlayerGameLog endpoint

## Raw available fields
SEASON_ID
Player_ID
Game_ID
GAME_DATE
MATCHUP
WL
MIN
FGM
FGA
FG_PCT
FG3M
FG3A
FG3_PCT
FTM
FTA
FT_PCT
OREB
DREB
REB
AST
STL
BLK
TOV
PF
PTS
PLUS_MINUS
VIDEO_AVAILABLE

## Prediction target
PTS for the player's next game

## Recommended candidate features
- minutes
- field goal attempts
- three-point attempts
- free throw attempts
- field goal percentage
- rebounds
- assists
- turnovers
- plus/minus
- home/away
- opponent
- season points average
- last-5 points average
- last-10 points average
- last-5 minutes average

## Important rule
All rolling features must use games occurring before the target game to avoid data leakage.