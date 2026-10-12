import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg

from data.ingestion.database_ingestion import get_database_url

# Version of the dataset structure and generation process.
DATASET_VERSION = "1.0.0"

MODELING_COLUMNS = [
    "player_id",
    "game_id",
    "game_date",
    "minutes",
    "points",
    "rebounds",
    "assists",
    "plus_minus",
    "opponent_team_id",
    "is_home",
    "recent_minutes_avg",
]

SORT_ORDER = [
    "player_id",
    "game_date",
    "game_id",
]


def load_modeling_data() -> pd.DataFrame:
    """
    Load historical NBA player game data from PostgreSQL.

    This function performs read-only queries and does not modify
    the stored historical records.
    """

    database_url = get_database_url()

    query = """
        SELECT
            pgs.player_id,
            pgs.game_id,
            g.game_date,
            pgs.minutes,
            pgs.points,
            pgs.rebounds,
            pgs.assists,
            pgs.plus_minus,
            pgs.opponent_team_id,
            pgs.is_home,
            pgs.recent_minutes_avg
        FROM player_game_stats pgs
        JOIN games g
            ON pgs.game_id = g.id
        ORDER BY
            pgs.player_id,
            g.game_date,
            pgs.game_id
    """

    with psycopg.connect(database_url) as connection:
        cursor = connection.execute(query)

        rows = cursor.fetchall()

        column_names = [
            description.name
            for description in cursor.description
        ]

    return pd.DataFrame(
        rows,
        columns=column_names,
    )


def build_modeling_dataset(
    source_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build a deterministic modeling dataset.

    If source_data is not provided, historical data is loaded
    from PostgreSQL.

    The returned DataFrame is a copy and does not modify
    the original source data.
    """

    if source_data is None:
        source_data = load_modeling_data()

    missing_columns = [
        column
        for column in MODELING_COLUMNS
        if column not in source_data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required modeling columns: "
            f"{missing_columns}"
        )

    dataset = source_data[MODELING_COLUMNS].copy()

    dataset = dataset.sort_values(
        by=SORT_ORDER,
        kind="stable",
    ).reset_index(drop=True)

    return dataset


def calculate_dataset_hash(
    dataset: pd.DataFrame,
) -> str:
    """
    Calculate a deterministic SHA-256 fingerprint.

    Identical dataset contents produce the same hash.
    Changes to the dataset produce a different hash.
    """

    csv_content = dataset.to_csv(
        index=False,
        lineterminator="\n",
    )

    return hashlib.sha256(
        csv_content.encode("utf-8")
    ).hexdigest()


def save_modeling_dataset(
    dataset: pd.DataFrame,
    output_directory: str | Path = "data/modeling",
) -> tuple[Path, Path]:
    """
    Save a versioned modeling dataset and metadata file.

    The dataset version identifies the generation process.
    The SHA-256 hash identifies the exact dataset contents.
    """

    output_path = Path(output_directory)

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset_hash = calculate_dataset_hash(dataset)

    hash_identifier = dataset_hash[:12]

    base_filename = (
        f"nba_modeling_dataset_"
        f"v{DATASET_VERSION}_"
        f"{hash_identifier}"
    )

    dataset_path = output_path / f"{base_filename}.csv"

    metadata_path = (
        output_path
        / f"{base_filename}.metadata.json"
    )

    dataset.to_csv(
        dataset_path,
        index=False,
        lineterminator="\n",
    )

    metadata = {
        "dataset_version": DATASET_VERSION,
        "generation_identifier": hash_identifier,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "row_count": len(dataset),
        "columns": list(dataset.columns),
        "sort_order": SORT_ORDER,
        "sha256": dataset_hash,
        "source": (
            "PostgreSQL games and player_game_stats tables"
        ),
        "generation_method": (
            "data.processing.modeling_dataset."
            "build_modeling_dataset"
        ),
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(
            metadata,
            metadata_file,
            indent=2,
        )

    return dataset_path, metadata_path


def main():
    dataset = build_modeling_dataset()

    dataset_path, metadata_path = (
        save_modeling_dataset(dataset)
    )

    dataset_hash = calculate_dataset_hash(dataset)

    print(f"Dataset version: {DATASET_VERSION}")
    print(f"Rows: {len(dataset)}")
    print(f"SHA-256: {dataset_hash}")
    print(f"Dataset saved to: {dataset_path}")
    print(f"Metadata saved to: {metadata_path}")


if __name__ == "__main__":
    main()