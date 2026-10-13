# Sprint 3 Modeling Dataset Validation

## Purpose

This document records manual validation performed for SCRUM-65.

The Sprint 3 modeling dataset was compared against the historical NBA
source data used during ingestion to verify that stored and generated
modeling values remain accurate.

## Automated Validation

Automated tests validate:

- Required modeling fields
- Opponent identifiers
- Home/away Boolean format
- Recent-minutes values
- Required-field null handling
- Numeric field types
- Dataset schema reproducibility
- Dataset record reproducibility
- Dataset SHA-256 reproducibility
- Clear reporting of missing required fields

Tests are located in:

`tests/test_modeling_dataset_validation.py`

## Manual Source Comparison

Several player-game records should be compared against the original
NBA source data.

| Player | Game | Field | Database Value | Source Value | Result |
|---|---|---|---|---|---|
| TBD | TBD | points | TBD | TBD | TBD |
| TBD | TBD | minutes | TBD | TBD | TBD |
| TBD | TBD | opponent | TBD | TBD | TBD |
| TBD | TBD | home/away | TBD | TBD | TBD |
| TBD | TBD | rebounds | TBD | TBD | TBD |

These values should be completed during the Sprint 3 validation cycle.

## Reproducibility

Dataset generation should be executed at least twice without modifying
the source database.

Both generations should produce:

- The same schema
- The same record ordering
- The same record values
- The same SHA-256 dataset hash

The metadata generation timestamp may differ between runs and is not
included in the dataset hash.