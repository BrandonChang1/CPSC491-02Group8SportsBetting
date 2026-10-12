import json

import pandas as pd
import pytest

from data.processing.modeling_dataset import (
    DATASET_VERSION,
    MODELING_COLUMNS,
    build_modeling_dataset,
    calculate_dataset_hash,
    save_modeling_dataset,
)


def make_source_data():
    return pd.DataFrame(
        [
            {
                "player_id": 201939,
                "game_id": "002",
                "game_date": pd.Timestamp("2025-10-23"),
                "minutes": 37,
                "points": 25,
                "rebounds": 5,
                "assists": 6,
                "plus_minus": 4,
                "opponent_team_id": 1610612743,
                "is_home": True,
                "recent_minutes_avg": 32.0,
            },
            {
                "player_id": 201939,
                "game_id": "001",
                "game_date": pd.Timestamp("2025-10-21"),
                "minutes": 32,
                "points": 23,
                "rebounds": 4,
                "assists": 7,
                "plus_minus": 2,
                "opponent_team_id": 1610612747,
                "is_home": False,
                "recent_minutes_avg": None,
            },
        ]
    )


def test_build_modeling_dataset_has_required_columns():
    source_data = make_source_data()

    dataset = build_modeling_dataset(source_data)

    assert list(dataset.columns) == MODELING_COLUMNS


def test_build_modeling_dataset_is_deterministically_sorted():
    source_data = make_source_data()

    dataset = build_modeling_dataset(source_data)

    assert dataset.iloc[0]["game_id"] == "001"
    assert dataset.iloc[1]["game_id"] == "002"


def test_build_modeling_dataset_does_not_modify_source():
    source_data = make_source_data()

    original = source_data.copy(deep=True)

    build_modeling_dataset(source_data)

    pd.testing.assert_frame_equal(
        source_data,
        original,
    )


def test_build_modeling_dataset_rejects_missing_columns():
    source_data = make_source_data().drop(
        columns=["opponent_team_id"]
    )

    with pytest.raises(
        ValueError,
        match="Missing required modeling columns",
    ):
        build_modeling_dataset(source_data)


def test_same_data_produces_same_hash():
    source_data = make_source_data()

    first_dataset = build_modeling_dataset(
        source_data
    )

    second_dataset = build_modeling_dataset(
        source_data
    )

    assert (
        calculate_dataset_hash(first_dataset)
        == calculate_dataset_hash(second_dataset)
    )


def test_changed_data_produces_different_hash():
    source_data = make_source_data()

    first_dataset = build_modeling_dataset(
        source_data
    )

    changed_data = source_data.copy(deep=True)
    changed_data.loc[0, "minutes"] = 40

    second_dataset = build_modeling_dataset(
        changed_data
    )

    assert (
        calculate_dataset_hash(first_dataset)
        != calculate_dataset_hash(second_dataset)
    )


def test_save_modeling_dataset_creates_files(
    tmp_path,
):
    source_data = make_source_data()

    dataset = build_modeling_dataset(source_data)

    dataset_path, metadata_path = (
        save_modeling_dataset(
            dataset,
            output_directory=tmp_path,
        )
    )

    assert dataset_path.exists()
    assert metadata_path.exists()

    assert (
        f"v{DATASET_VERSION}"
        in dataset_path.name
    )


def test_metadata_contains_version_and_hash(
    tmp_path,
):
    source_data = make_source_data()

    dataset = build_modeling_dataset(source_data)

    dataset_path, metadata_path = (
        save_modeling_dataset(
            dataset,
            output_directory=tmp_path,
        )
    )

    with metadata_path.open(
        "r",
        encoding="utf-8",
    ) as metadata_file:
        metadata = json.load(metadata_file)

    expected_hash = calculate_dataset_hash(dataset)

    assert (
        metadata["dataset_version"]
        == DATASET_VERSION
    )

    assert metadata["sha256"] == expected_hash

    assert metadata["row_count"] == len(dataset)

    assert metadata["columns"] == MODELING_COLUMNS

    assert "generated_at" in metadata

    assert "generation_identifier" in metadata

    assert (
        metadata["generation_identifier"]
        in dataset_path.name
    )