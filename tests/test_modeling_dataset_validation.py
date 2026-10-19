import pandas as pd
import pytest

from data.processing.modeling_dataset import (
    MODELING_COLUMNS,
    build_modeling_dataset,
    calculate_dataset_hash,
)


def make_modeling_source():
    return pd.DataFrame(
        [
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
                "game_id": "003",
                "game_date": pd.Timestamp("2025-10-24"),
                "minutes": 27,
                "points": 20,
                "rebounds": 3,
                "assists": 8,
                "plus_minus": -1,
                "opponent_team_id": 1610612757,
                "is_home": False,
                "recent_minutes_avg": 34.5,
            },
        ]
    )


def test_required_modeling_fields_are_present():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    assert list(dataset.columns) == MODELING_COLUMNS


def test_opponent_field_is_present_and_valid():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    assert dataset["opponent_team_id"].notna().all()

    assert (
        pd.api.types.is_integer_dtype(
            dataset["opponent_team_id"]
        )
    )


def test_home_away_field_uses_boolean_format():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    assert dataset["is_home"].notna().all()

    assert (
        pd.api.types.is_bool_dtype(
            dataset["is_home"]
        )
    )


def test_recent_minutes_is_correctly_available():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    first_row = dataset.iloc[0]

    assert pd.isna(
        first_row["recent_minutes_avg"]
    )

    assert (
        dataset.iloc[1]["recent_minutes_avg"]
        == 32.0
    )

    assert (
        dataset.iloc[2]["recent_minutes_avg"]
        == 34.5
    )


def test_required_fields_do_not_have_unexpected_nulls():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    required_non_null_columns = [
        "player_id",
        "game_id",
        "game_date",
        "minutes",
        "points",
        "rebounds",
        "assists",
        "opponent_team_id",
        "is_home",
    ]

    for column in required_non_null_columns:
        assert dataset[column].notna().all()


def test_numeric_fields_have_numeric_types():
    dataset = build_modeling_dataset(
        make_modeling_source()
    )

    numeric_columns = [
        "player_id",
        "minutes",
        "points",
        "rebounds",
        "assists",
        "plus_minus",
        "opponent_team_id",
        "recent_minutes_avg",
    ]

    for column in numeric_columns:
        assert pd.api.types.is_numeric_dtype(
            dataset[column]
        )


def test_repeated_generation_has_same_schema():
    source = make_modeling_source()

    first = build_modeling_dataset(source)
    second = build_modeling_dataset(source)

    assert list(first.columns) == list(second.columns)

    assert first.dtypes.astype(str).tolist() == (
        second.dtypes.astype(str).tolist()
    )


def test_repeated_generation_has_same_record_set():
    source = make_modeling_source()

    first = build_modeling_dataset(source)
    second = build_modeling_dataset(source)

    pd.testing.assert_frame_equal(
        first,
        second,
    )


def test_repeated_generation_has_same_hash():
    source = make_modeling_source()

    first = build_modeling_dataset(source)
    second = build_modeling_dataset(source)

    assert (
        calculate_dataset_hash(first)
        == calculate_dataset_hash(second)
    )


def test_missing_required_field_is_reported_clearly():
    source = make_modeling_source().drop(
        columns=["opponent_team_id"]
    )

    with pytest.raises(
        ValueError,
        match="Missing required modeling columns",
    ):
        build_modeling_dataset(source)