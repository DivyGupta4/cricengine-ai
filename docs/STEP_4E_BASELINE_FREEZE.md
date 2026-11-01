# CricEngine AI — Step 4E Baseline Freeze & Integrity Record

**Date**: 2026-10-30T12:25:00+05:30  
**Status**: FROZEN & VERIFIED  
**Curated Database**: `data/datalake/curated/cricengine.duckdb` (Strictly Read-Only)  
**Feature Store Root**: `data/datalake/feature_store/`  
**Full Checksum Manifest**: [`docs/feature_store_baseline_checksums.json`](file:///Users/divygupta/Desktop/DL_DATABASE/docs/feature_store_baseline_checksums.json) (1,167 individual files)  

---

## 1. Baseline Preservation Overview

This document formally records and freezes the complete architectural, database, and feature-store state established at the conclusion of **Phase 1: Step 4E Pipeline Remediation**. 

All materialized datasets, configuration catalogs, and the production curated database are permanently locked under this baseline. During the subsequent Phase 2 Data Quality Audit, these datasets will remain strictly unmodified and read-only.

---

## 2. Environment & Working-Tree State

- **Host OS**: macOS (Apple Silicon Darwin)
- **Virtual Environment**: `.venv` (Python 3.12.10)
- **Core Dependencies**:
  - `duckdb`: 2.0.0
  - `pyarrow`: 26.0.0
  - `pandas`: 3.1.0
  - `pytest`: 9.2.0
- **Git State**:
  - Current Branch: `main`
  - Working Tree: Clean untracked state (0 staged files, 0 commits). No commits created per authorization policy.
  - Raw Cricsheet archives and manifests preserved intact in `data/datalake/raw/`.

---

## 3. Production Database State

The curated production database contains 9,085 ingested canonical matches across 7,014 canonical players and 4,383,700 ball-by-ball delivery records.

| Attribute | Baseline Value |
|---|---|
| **Database Path** | `data/datalake/curated/cricengine.duckdb` |
| **Exact Byte Size** | `401,616,896` bytes (383.01 MB) |
| **Streaming SHA-256 Checksum** | `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae` |
| **Access Mode** | Strict `read_only=True` |

---

## 4. Key Configuration and Metadata Checksums

| File Path | Byte Size | Streaming SHA-256 Checksum |
|---|---|---|
| [`config/canonical_venues.json`](file:///Users/divygupta/Desktop/DL_DATABASE/config/canonical_venues.json) | 131,900 | `91d055da2a52275c41bf19ea7b7a7cf67a532e6f7aed66950a5bed9347f3c597` |
| `data/datalake/feature_store/_manifest.json` | 2,448 | `92b4699e748e33c7dcb2b90e34b6ee247bbb35a97121c04b4c201223c599ddce` |
| `data/datalake/feature_store/feature_metadata/feature_catalog_v1.json` | 6,331 | `891f72e1d5aab8b67a3aa22c4a097d8637ce5f4b2737791963d4f716ca28417e` |
| `data/datalake/feature_store/feature_metadata/transformation_lineage.json` | 1,147 | `218741a74a35bca47a6fae32de0c168d7695f07a460f3fb65ada5c882a30147c` |

### Contextual Baselines Parquet Checksums

| Baseline File | Row Count | Byte Size | Streaming SHA-256 Checksum |
|---|---|---|---|
| `contextual_baselines/venue_park_factors.parquet` | 824 | 29,207 | `157be8b35b3ee830b29de635d01645b42c6cccc28b32e823910ebe2c5211fd10` |
| `contextual_baselines/phase_scoring_baselines.parquet` | 11 | 7,014 | `8d7bee6b9427997bfa5bee02153460fc21def0479a79826f246b4b5151393c5e` |
| `contextual_baselines/opposition_bowling_baselines.parquet` | 206 | 14,287 | `34b30550874df78f4c2ad038c54790a5edb574d45385116976a7b261ce0a6263` |
| `contextual_baselines/opposition_batting_baselines.parquet` | 206 | 14,283 | `b690e87a779ba93924d935cf1358850519ad529c6d4c92e2a91a1d14abd6930f` |

---

## 5. Dataset Inventory, Row Counts & Schemas

The feature store consists of 1,167 materialized files in total:
- 1,160 partitioned Parquet files
- 4 unpartitioned contextual baselines Parquet files
- 2 JSON metadata files
- 1 root `_manifest.json`

```
data/datalake/feature_store/
├── _manifest.json
├── feature_metadata/
│   ├── feature_catalog_v1.json
│   └── transformation_lineage.json
├── contextual_baselines/
│   ├── venue_park_factors.parquet           [824 rows, Snappy]
│   ├── phase_scoring_baselines.parquet      [11 rows, Snappy]
│   ├── opposition_bowling_baselines.parquet  [206 rows, Snappy]
│   └── opposition_batting_baselines.parquet  [206 rows, Snappy]
├── player_match/                            [200,709 rows, 46 cols, 145 partition files]
├── rolling_match/                           [602,127 rows, 34 cols, 435 partition files]
├── rolling_time/                            [602,127 rows, 19 cols, 435 partition files]
└── contextual_features/                     [200,709 rows, 18 cols, 145 partition files]
```

### Summary of Dataset Metrics

| Dataset Name | Total Rows | Columns | Partitions | File Count | Partitioning Structure |
|---|---|---|---|---|---|
| `player_match` | 200,709 | 46 | 145 | 145 | `match_format`, `season` |
| `rolling_match` | 602,127 | 34 | 435 | 435 | `match_format`, `window_size` (5, 10, 20), `season` |
| `rolling_time` | 602,127 | 19 | 435 | 435 | `match_format`, `window_days` (30, 90, 365), `season` |
| `contextual_features` | 200,709 | 18 | 145 | 145 | `match_format`, `season` |
| `contextual_baselines` | 1,247 | Varies | 4 | 4 | Single Snappy Parquet files |
| **Total** | **1,606,919** | — | — | **1,164 Parquet files** | — |

---

## 6. Complete Schema Contracts

### `PLAYER_MATCH_SCHEMA` (46 Columns)
```python
pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("competition_name", pa.string()),
    ("competition_tier", pa.int8()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("start_date", pa.date32()),
    ("team_name", pa.string()),
    ("opposition_team", pa.string()),
    ("venue_name", pa.string()),
    ("canonical_venue_name", pa.string()),
    ("city", pa.string()),
    ("participation_role", pa.string()),
    ("in_starting_xi", pa.bool_()),
    ("has_batted", pa.bool_()),
    ("has_bowled", pa.bool_()),
    ("has_fielded", pa.bool_()),
    ("batting_position", pa.int8()),
    ("runs_scored", pa.int16()),
    ("balls_faced", pa.int16()),
    ("boundary_fours", pa.int8()),
    ("boundary_sixes", pa.int8()),
    ("dot_balls_faced", pa.int16()),
    ("is_dismissed", pa.bool_()),
    ("dismissals_count", pa.int8()),
    ("dismissal_kind", pa.string()),
    ("strike_rate", pa.float32()),
    ("boundary_pct", pa.float32()),
    ("dot_pct_faced", pa.float32()),
    ("legal_balls_bowled", pa.int16()),
    ("overs_bowled", pa.float32()),
    ("runs_conceded", pa.int16()),
    ("wickets_credited", pa.int8()),
    ("dot_balls_bowled", pa.int16()),
    ("boundaries_conceded", pa.int16()),
    ("maiden_overs", pa.int8()),
    ("economy_rate", pa.float32()),
    ("bowling_strike_rate", pa.float32()),
    ("bowling_average", pa.float32()),
    ("catches_taken", pa.int8()),
    ("stumpings_taken", pa.int8()),
    ("runouts_involved", pa.int8()),
    ("total_fielding_involvements", pa.int8()),
    ("batting_load", pa.float32()),
    ("bowling_load", pa.float32()),
    ("allrounder_balance_index", pa.float32()),
])
```

### `ROLLING_MATCH_SCHEMA` (34 Columns)
```python
pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("window_size", pa.int8()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("matches_in_window", pa.int8()),
    ("rolling_runs_scored", pa.int32()),
    ("rolling_balls_faced", pa.int32()),
    ("rolling_dismissals_count", pa.int16()),
    ("rolling_batting_sr", pa.float32()),
    ("rolling_batting_avg", pa.float32()),
    ("rolling_boundary_pct", pa.float32()),
    ("rolling_dot_pct_faced", pa.float32()),
    ("rolling_legal_balls_bowled", pa.int32()),
    ("rolling_overs_bowled", pa.float32()),
    ("rolling_runs_conceded", pa.int32()),
    ("rolling_wickets_taken", pa.int16()),
    ("rolling_economy_rate", pa.float32()),
    ("rolling_bowling_sr", pa.float32()),
    ("rolling_bowling_avg", pa.float32()),
    ("rolling_dot_pct_bowled", pa.float32()),
    ("rolling_maidens_count", pa.int16()),
    ("rolling_catches", pa.int16()),
    ("rolling_stumpings", pa.int16()),
    ("rolling_runouts", pa.int16()),
    ("decayed_batting_sr", pa.float32()),
    ("decayed_economy_rate", pa.float32()),
    ("shrunk_batting_sr", pa.float32()),
    ("shrunk_economy_rate", pa.float32()),
    ("mean_batting_load", pa.float32()),
    ("mean_bowling_load", pa.float32()),
    ("mean_allrounder_index", pa.float32()),
    ("days_since_last_match", pa.int16()),
])
```

### `ROLLING_TIME_SCHEMA` (19 Columns)
```python
pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("window_days", pa.int16()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("matches_in_window", pa.int8()),
    ("rolling_runs_scored", pa.int32()),
    ("rolling_balls_faced", pa.int32()),
    ("rolling_dismissals_count", pa.int16()),
    ("rolling_batting_sr", pa.float32()),
    ("rolling_batting_avg", pa.float32()),
    ("rolling_legal_balls_bowled", pa.int32()),
    ("rolling_runs_conceded", pa.int32()),
    ("rolling_wickets_taken", pa.int16()),
    ("rolling_economy_rate", pa.float32()),
    ("decayed_batting_sr", pa.float32()),
    ("decayed_economy_rate", pa.float32()),
    ("days_since_last_match", pa.int16()),
])
```

### `CONTEXTUAL_FEATURES_SCHEMA` (18 Columns)
```python
pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("venue_name", pa.string()),
    ("canonical_venue_name", pa.string()),
    ("opposition_team", pa.string()),
    ("venue_historical_park_factor", pa.float32()),
    ("opposition_bowling_quality_index", pa.float32()),
    ("opposition_batting_quality_index", pa.float32()),
    ("is_home_match", pa.bool_()),
    ("is_neutral_match", pa.bool_()),
    ("competition_tier_multiplier", pa.float32()),
    ("career_powerplay_strike_rate", pa.float32()),
    ("career_death_strike_rate", pa.float32()),
    ("career_powerplay_economy", pa.float32()),
    ("career_death_economy", pa.float32()),
])
```

---

## 7. Automated Test Suite Results

All 54 tests in the test suite pass with 100% success rate:
- `tests/test_acquisition.py`: 11 passed
- `tests/test_data_leakage.py`: 4 passed
- `tests/test_environment.py`: 6 passed
- `tests/test_feature_store.py`: 12 passed
- `tests/test_parser_schema.py`: 17 passed
- `tests/test_rolling_features.py`: 4 passed

---

## 8. Known Limitations of the Baseline

1. **Non-Strikers With Zero Balls Faced Not Out**:
   1,505 player-matches correspond to batsmen at the crease who did not face a ball and were not out when the match/innings concluded. Under cricket conventions, these are unobserved in ball-by-ball striking (`has_batted=FALSE`, `balls_faced=NULL`, `runs_scored=NULL`), which correctly preserves zero-conflation semantics.
2. **Phase Career Placeholders**:
   `career_powerplay_strike_rate`, `career_death_strike_rate`, `career_powerplay_economy`, and `career_death_economy` currently emit `NULL` placeholders in `contextual_features` until phase-specific point-in-time window models are calibrated in Phase 3.
3. **Franchise Home Ground Coverage**:
   IPL home status derivation is mapped for 10 current IPL franchises across 28 venue strings. Associate or multi-franchise neutral fixtures outside this mapping default to `is_neutral_match = TRUE`.
4. **Historical Venue Renaming**:
   527 raw venue names are mapped to 500 canonical grounds. Venues with genuine physical transformations (e.g. Adelaide Oval vs Adelaide Oval No 2) remain distinct, ensuring historical park factor integrity.

---

## 9. Baseline Declaration

The Step 4E baseline is **FROZEN**. All 1,167 files and their SHA-256 hashes in `docs/feature_store_baseline_checksums.json` constitute the definitive reference point for the Phase 2 audit.
