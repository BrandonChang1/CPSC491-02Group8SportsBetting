# Sprint 1 Prediction & Analytics Design

This Sprint 1 work is a small proof of concept for **next-game points** prediction. It uses only synthetic sample data; it does not call an NBA API, train a model, calculate betting probabilities, or build an application endpoint.

## Prediction Target

The future model will predict a player's **next-game points**.

For a prediction made before game *t + 1*, features must be calculated only from information available through game *t*. The points scored in game *t + 1* become the target. For example:

- Available before the next game: season average = 25.1, last-5 average = 27.2, previous-game points = 29, recent average minutes = 35.1
- Target: next-game points = 31

This chronological setup prevents future-game statistics from leaking into features.

## Sample Dataset

`data/sample_nba_games.csv` contains 152 synthetic NBA-style game rows: 8 recognizable players with 19 chronological games each. The player names are recognizable for readability, but every team assignment, opponent, date, and statistic is sample data only.

## Initial Features

Sprint 1 proposes a deliberately small feature set:

- Season points average before the predicted game
- Last-5-games points average
- Previous-game points
- Recent average minutes
- Home/away for the game being predicted

Opponent can be added later as a matchup feature. Home/away and opponent should come from the known upcoming schedule, while the statistical features must use only completed earlier games.

## Training and Testing Approach

NBA player games are chronological time-series data. A future model should train on older games and test on newer games, such as roughly the oldest 80% for training and newest 20% for testing. It must not randomly mix future games into training data used to predict earlier games.

No model is trained in Sprint 1.

## Baseline

The initial baseline is the player's last-5-games points average. For each upcoming game, predict that average as the next-game points estimate.

Later, Linear Regression and Random Forest can be evaluated against this baseline. A later model is useful only if it improves on the baseline using the same chronological test set.

## Required Data Fields

| Field | Purpose |
| --- | --- |
| `player_id` | Stable identifier for grouping a player's game history |
| `player_name` | Human-readable name for results and UI |
| `game_date` | Required to order games chronologically and split train/test data |
| `team` | Player team context; useful for future roster/team features |
| `opponent` | Possible future matchup feature |
| `home_away` | Possible game-context feature for the game being predicted |
| `minutes` | Used to calculate recent playing-time average |
| `points` | Used to calculate historical scoring averages and the next-game target |
| `rebounds` | Optional later performance/context feature |
| `assists` | Optional later performance/context feature |
| `field_goal_attempts` | Optional later opportunity/usage feature |

## Future Model Input/Output

Conceptual future input:

```json
{
  "player_id": 1,
  "season_points_avg": 25.1,
  "last_5_points_avg": 27.2,
  "previous_game_points": 29,
  "recent_minutes_avg": 35.1,
  "home_away": "HOME"
}
```

Conceptual future output:

```json
{
  "player_name": "LeBron James",
  "predicted_points": 26.4
}
```

This is a design only; no API is created in Sprint 1.

## Future UI Prediction Result

A future prediction result screen should display:

- Player name
- Season points average
- Recent points average
- Predicted next-game points

Later sprints can add a sportsbook/prop line, over/under probability, and risk or confidence information.

## Next Steps

1. Replace or supplement the sample data with a validated historical NBA source.
2. Build leakage-safe feature creation using completed prior games and upcoming schedule context.
3. Apply a chronological 80/20-style split, measure the last-5 baseline, and then compare simple regression models.
4. Add betting-line probability and risk work only after next-game points prediction has been evaluated.

