"""Train and evaluate a reproducible random-forest next-game points model from feature CSV.

Run from the repository root: python -m ml.training.train_tree_points
Input features are lagged/prior-game statistics, avoiding target leakage.
Train/test come from ml.training.evaluation.holdout_split (chronological,
multi-player holdout), and the model is scored against the baselines on the
same held-out rows. save_model writes the model, its manifest (with this
config and these metrics) and a "candidate" entry in ml/models/registry.json.
"""
import json
from pathlib import Path

import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from ml.model_integrity import save_model, sha256_file
from ml.training.evaluation import (
    FEATURES,
    MIN_TEST_PLAYERS,
    TARGET,
    TRAIN_FRACTION,
    evaluate_model,
    holdout_split,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/sample/player_game_stats_sample_features.csv'
MODEL_NAME = 'random-forest-points'
FOREST_PARAMS = {'n_estimators': 120, 'min_samples_leaf': 4, 'random_state': 42, 'n_jobs': -1}


def main():
    holdout = holdout_split(load_dataset(DATA))
    model = Pipeline([
        ('imputer', SimpleImputer(strategy='median', add_indicator=False)),
        ('forest', RandomForestRegressor(**FOREST_PARAMS)),
    ])
    model.fit(holdout.train[FEATURES], holdout.train[TARGET])

    training_config = {
        'training_script': 'ml/training/train_tree_points.py',
        'evaluation_module': 'ml/training/evaluation.py',
        'estimator': 'Pipeline(SimpleImputer(strategy=median) -> RandomForestRegressor)',
        'forest_params': FOREST_PARAMS,
        'features': FEATURES,
        'target': TARGET,
        'train_fraction': TRAIN_FRACTION,
        'min_test_players': MIN_TEST_PLAYERS,
        'dataset': str(DATA.relative_to(ROOT)),
        'dataset_sha256': sha256_file(DATA),
        'holdout': holdout.summary(),
        'scikit_learn_version': sklearn.__version__,
    }
    metrics = evaluate_model(model, holdout, MODEL_NAME)
    entry = save_model(
        model,
        model_name=MODEL_NAME,
        features=holdout.train[FEATURES],
        dataset_path=DATA,
        training_config=training_config,
        evaluation_metrics=metrics,
    )
    print(json.dumps({'saved': entry['model_version'], 'status': entry['status'], 'test': metrics['test'],
                      'best_baseline': metrics['best_baseline'], 'beats_best_baseline': metrics['beats_best_baseline'],
                      'artifact': entry['artifact_path'], 'manifest': entry['manifest_path']}))


if __name__ == '__main__':
    main()
