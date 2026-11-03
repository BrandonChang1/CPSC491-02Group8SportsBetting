"""Train a reproducible random-forest next-game points model from feature CSV.

Run from the repository root: python -m ml.training.train_tree_points
Input features are lagged/prior-game statistics, avoiding target leakage.
"""
from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/sample/player_game_stats_sample_features.csv'
OUTPUT = ROOT / 'ml/models/artifacts/random_forest_points.joblib'
FEATURES = ['pts_season_avg', 'pts_last5_avg', 'pts_last10_avg', 'is_home', 'recent_minutes_avg']


def main():
    data = pd.read_csv(DATA)
    data['game_date'] = pd.to_datetime(data['game_date'], errors='coerce')
    for field in FEATURES + ['points']:
        data[field] = pd.to_numeric(data[field], errors='coerce')
    # Need past results for each player; split labels are precomputed chronologically.
    data = data.dropna(subset=['game_date', 'points', 'pts_last5_avg'])
    train = data[data['split'] == 'train']
    test = data[data['split'] == 'test']
    if train.empty or test.empty:
        raise ValueError('Expected nonempty chronological train and test subsets')
    model = Pipeline([
        ('imputer', SimpleImputer(strategy='median', add_indicator=False)),
        ('forest', RandomForestRegressor(n_estimators=120, min_samples_leaf=4, random_state=42, n_jobs=-1)),
    ])
    model.fit(train[FEATURES], train['points'])
    mae = mean_absolute_error(test['points'], model.predict(test[FEATURES]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'features': FEATURES, 'pipeline': model}, OUTPUT)
    print(json.dumps({'model': 'random-forest-points-v1', 'train_rows': len(train), 'test_rows': len(test), 'test_mae_points': round(float(mae), 3), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()
