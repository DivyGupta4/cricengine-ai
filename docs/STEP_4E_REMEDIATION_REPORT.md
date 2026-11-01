# CricEngine AI — Phase 1: Step 4E Pipeline Remediation Report

**Date**: 2026-10-30  
**Phase**: Phase 1 — Step 4E: Feature Store Pipeline Remediation  
**Status**: COMPLETED & VERIFIED (54/54 Tests Passing, DuckDB Immutability Proven)  
**Database**: `data/datalake/curated/cricengine.duckdb` (Strictly Read-Only)  
**Feature Store Destination**: `data/datalake/feature_store/`  

---

## 1. Executive Summary

Under explicit authorization for **Phase 1: Step 4E Pipeline Remediation**, all five architectural and mathematical defects identified during the Step 4B/4C/4D feature engineering audit have been systematically resolved, end-to-end regression tested, and deterministically materialized into the Feature Store.

### Remediation Objectives & Outcomes

| Remediation Item | Target Defect | Implementation Scope | Verification Result |
|---|---|---|---|
| **1. Diamond-Duck Accounting** | 324 batters dismissed without facing a ball were omitted from batting participation (`has_batted=FALSE`, `is_dismissed=FALSE`). | Crease entry rank extended to dismissals/non-strikers; full outer join sets `has_batted=TRUE`, `runs_scored=0`, `balls_faced=0`, `is_dismissed=TRUE`, `dismissals_count=1`, `strike_rate=NULL`. | **PASSED**: All 324 diamond ducks reconciled without duplicate participation rows. |
| **2. Caught-and-Bowled Attribution** | 3,860 caught-and-bowled dismissals had 0 entries in `fact_dismissal_fielder`; bowlers received zero fielding catch credits. | Unioned outfield catches with bowler caught-and-bowled events into unified fielding aggregation. | **PASSED**: Exactly 1 catch credited to bowler per C&B dismissal; dataset catches increased from 79,585 to 83,445 without double-counting wickets. |
| **3. Multi-Innings Test Dismissals** | 11,036 Test player-matches had 2 dismissals collapsed to boolean 1, inflating rolling batting averages. | Added `dismissals_count INT8` (0, 1, 2) to schema; updated rolling windows to compute `SUM(dismissals_count)`. | **PASSED**: True multi-innings dismissals counted (11,036 rows with count=2); rolling averages accurately reflect multi-innings denominators. |
| **4. Canonical Venue Mapping** | 527 raw venue strings fragmented sample sizes across string aliases in expanding park factors. | Generated `config/canonical_venues.json` mapping 527 raw venues to 500 canonical grounds; added `canonical_venue_name` to schemas and partitioned park factors by canonical ground. | **PASSED**: 100% of rows have non-null canonical venue; `venue_park_factors.parquet` consolidated from 885 to 824 format-venue rows. |
| **5. Opposition Batting Baselines** | `opposition_batting_baselines.parquet` missing from `contextual_baselines/`. | Aggregated and serialized team batting scoring rate and batting average across format-team grain. | **PASSED**: Materialized `opposition_batting_baselines.parquet` (206 rows) alongside opposition bowling baselines. |

---

## 2. Curated Database Immutability Verification

To guarantee that the production database remained strictly unmodified throughout pipeline execution, streaming SHA-256 checksums and exact byte sizes were verified before and after execution:

| Verification Phase | Byte Size | SHA-256 Checksum | Immutability Status |
|---|---|---|---|
| **Pre-Execution Baseline** | 401,616,896 bytes (383.01 MB) | `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae` | Established |
| **Pipeline Post-Execution Check** | 401,616,896 bytes (383.01 MB) | `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae` | **100% IDENTICAL** |
| **Independent Post-Test Verification** | 401,616,896 bytes (383.01 MB) | `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae` | **100% IDENTICAL** |

> [!IMPORTANT]
> The curated database `data/datalake/curated/cricengine.duckdb` was connected exclusively using `read_only=True`. Zero bytes, tables, or indexes in the database were created, altered, or deleted.

---

## 3. Detailed Technical Analysis of the Five Remediations

### Remediation 1: Diamond-Duck Dismissal Accounting

#### Root Cause
In Cricsheet ball-by-ball records, a player who is run out or timed out without facing a legal delivery appears in `fact_delivery_dismissal` (with `player_out_id`), but never appears as `batter_id` in `fact_ball_by_ball`. In Step 4B, batting aggregates were constructed strictly from `fact_ball_by_ball` grouped by `batter_id`. Consequently, joining on `p.player_id = b.player_id` yielded `NULL` for all 324 diamond ducks, causing `has_batted = FALSE`, `is_dismissed = FALSE`, `runs_scored = NULL`, and `balls_faced = NULL`.

#### Remediation Implementation
1. **Batting Position Crease Entry Expansion**:
   Extended the crease entry sequence CTE (`crease_entry`) to union deliveries where the player appeared as `batter_id`, `non_striker_id`, or `player_out_id` from `fact_delivery_dismissal`. All 324 diamond ducks now receive their true `batting_position` (e.g., position 9, 10, or 11).
2. **Reconciliation Logic**:
   ```sql
   CASE WHEN (b.player_id IS NOT NULL OR d.player_id IS NOT NULL) THEN TRUE ELSE FALSE END AS has_batted,
   CASE WHEN (b.player_id IS NOT NULL OR d.player_id IS NOT NULL) THEN CAST(bp.batting_position AS TINYINT) ELSE NULL END AS batting_position,
   CASE 
       WHEN b.player_id IS NOT NULL THEN CAST(b.runs_scored AS SMALLINT)
       WHEN d.player_id IS NOT NULL THEN CAST(0 AS SMALLINT)
       ELSE NULL 
   END AS runs_scored,
   CASE 
       WHEN b.player_id IS NOT NULL THEN CAST(b.balls_faced AS SMALLINT)
       WHEN d.player_id IS NOT NULL THEN CAST(0 AS SMALLINT)
       ELSE NULL 
   END AS balls_faced,
   CASE WHEN d.player_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_dismissed,
   CAST(COALESCE(d.dismissals_count, 0) AS TINYINT) AS dismissals_count,
   ```
3. **Zero-Conflation Policy Preservation**:
   Because `balls_faced = 0`, `strike_rate`, `boundary_pct`, and `dot_pct_faced` evaluate to `NULL` (never 0.0), maintaining strict statistical integrity.

#### Verification
- 363 total player-matches in `player_match` have `has_batted = TRUE` and `balls_faced = 0`:
  - 324 diamond ducks not in `fact_ball_by_ball` as batters (all with `is_dismissed = TRUE`, `runs_scored = 0`, `dismissals_count = 1`).
  - 11 batters who faced only wides and were dismissed (e.g. stumped off a wide).
  - 28 batters who faced only wides and remained not out.
- Zero duplicate player-match records created; total row count remains exactly 200,709.

---

### Remediation 2: Caught-and-Bowled Fielding Attribution

#### Root Cause
In Cricsheet JSON/relational models, fielders for outfield dismissals (`caught`, `stumped`, `run out`) are recorded in `fact_dismissal_fielder`. However, for caught-and-bowled dismissals (`dismissal_kind = 'caught and bowled'`), Cricsheet does not duplicate the bowler in the fielders array. Consequently, `fact_dismissal_fielder` contains 0 entries for all 3,860 caught-and-bowled dismissals, causing bowlers to receive zero catch credits in their fielding box scores.

#### Remediation Implementation
Constructed a disjoint union CTE `raw_fielding_events` in `etl/build_feature_store.py`:
```sql
raw_fielding_events AS (
    -- 1. Outfield catches, stumpings, and run outs
    SELECT 
        d.match_id,
        f.fielder_id AS player_id,
        CASE WHEN d.dismissal_kind = 'caught' THEN 1 ELSE 0 END AS is_catch,
        CASE WHEN d.dismissal_kind = 'stumped' THEN 1 ELSE 0 END AS is_stumping,
        CASE WHEN d.dismissal_kind = 'run out' THEN 1 ELSE 0 END AS is_runout
    FROM fact_dismissal_fielder f
    JOIN fact_delivery_dismissal d ON f.dismissal_id = d.dismissal_id
    
    UNION ALL
    
    -- 2. Bowler catches from caught and bowled dismissals
    SELECT 
        d.match_id,
        b.bowler_id AS player_id,
        1 AS is_catch,
        0 AS is_stumping,
        0 AS is_runout
    FROM fact_delivery_dismissal d
    JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
    WHERE d.dismissal_kind = 'caught and bowled'
)
```
- Bowling wickets credited (`bowler_wickets_agg`) remain derived strictly from `d.bowler_credited = TRUE`, ensuring bowlers receive 1 wicket and 1 catch without double-counting wickets.

#### Verification
- Total catches across all 200,709 player-matches:
  - Outfield catches: 79,585
  - Caught-and-bowled catches: 3,860
  - **New Total Catches**: 83,445 (exactly 79,585 + 3,860).
- Total fielding involvements: 98,786 (94,926 + 3,860).

---

### Remediation 3: Multi-Innings Test Dismissals Count

#### Root Cause
In Test matches, a player can be dismissed up to two times across two innings (1st innings and 2nd innings). Previously, `temp_player_match` defined `is_dismissed` as a boolean. In `rolling_features.py`, rolling dismissals were computed as:
```sql
SUM(CASE WHEN is_dismissed = TRUE THEN 1 ELSE 0 END) OVER w AS rolling_dismissals_count
```
This collapsed two dismissals into 1, under-counting dismissals for 11,036 Test player-matches and improperly deflating the denominator of rolling Test batting averages.

#### Remediation Implementation
1. **Schema Contract Update**:
   Added `("dismissals_count", pa.int8())` directly after `is_dismissed` in `PLAYER_MATCH_SCHEMA`.
2. **Extraction Aggregation**:
   ```sql
   dismissal_agg AS (
       SELECT 
           match_id,
           player_out_id AS player_id,
           TRUE AS is_dismissed,
           COUNT(*) AS dismissals_count,
           STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
       FROM fact_delivery_dismissal
       GROUP BY match_id, player_out_id
   )
   ```
3. **Rolling Features Computation**:
   Updated both `generate_rolling_match_features_df` and `generate_rolling_time_features_df` in `etl/rolling_features.py` to aggregate `SUM(dismissals_count)`:
   ```sql
   table_cols = [c[0] for c in con.execute(f"SELECT column_name FROM (DESCRIBE {player_match_table_or_view})").fetchall()]
   dismissal_col_expr = "COALESCE(dismissals_count, 0) AS dismissals_count" if "dismissals_count" in table_cols else "CASE WHEN is_dismissed = TRUE THEN 1 ELSE 0 END AS dismissals_count"
   ...
   SUM(dismissals_count) OVER w AS rolling_dismissals_count
   ```

#### Verification
- Distribution of `dismissals_count` across Test format (19,758 player-matches):
  - `dismissals_count = 0`: 1,914 player-matches
  - `dismissals_count = 1`: 6,808 player-matches
  - `dismissals_count = 2`: 11,036 player-matches
- Unit test `test_multi_innings_dismissals_in_rolling_average` confirms that a batsman dismissed twice in 5 Test matches has `rolling_dismissals_count = 10` and accurately computes average `500 / 10 = 50.0`.

---

### Remediation 4: Canonical Venue Mapping

#### Root Cause
527 distinct raw venue strings in Cricsheet caused sample size fragmentation. For example, Bengaluru fixtures were split across:
- `"M Chinnaswamy Stadium"` (106 matches)
- `"M. Chinnaswamy Stadium"` (3 matches)
- `"M Chinnaswamy Stadium, Bengaluru"` (7 matches)

Partitioning expanding park factors by raw `venue_name` fragmented the delivery sample across alias strings, delaying the 600-ball sample threshold.

#### Remediation Implementation
1. **Canonical Venue Catalog**:
   Generated [`config/canonical_venues.json`](file:///Users/divygupta/Desktop/DL_DATABASE/config/canonical_venues.json) mapping all 527 raw venue names to 500 canonical grounds, reconciling 51 alias pairs while strictly keeping distinct adjacent grounds separate (e.g. *Adelaide Oval* vs *Adelaide Oval No 2*, *Al Amerat Cricket Ground Turf 1* vs *Turf 2*).
2. **Schema Integration**:
   Added `("canonical_venue_name", pa.string())` directly after `venue_name` in both `PLAYER_MATCH_SCHEMA` and `CONTEXTUAL_FEATURES_SCHEMA`.
3. **Pipeline Joining**:
   Loaded `temp_venue_mapping` in DuckDB. In `temp_player_match` and `contextual_features`:
   ```sql
   COALESCE(vm.canonical_venue_name, c.venue_name) AS canonical_venue_name
   ```
4. **Expanding Park Factor & Baseline Consolidation**:
   Updated expanding park factor windows in `etl/contextual_features.py` and `generate_and_materialize_baselines()` in `etl/build_feature_store.py` to partition and group by `canonical_venue_name`.

#### Verification
- Raw distinct venues: 527
- Canonical distinct grounds: 500
- Null count of `canonical_venue_name`: exactly 0 (100% coverage).
- `venue_park_factors.parquet` row count consolidated from 885 to 824 format-venue combinations.

---

### Remediation 5: Opposition Batting Baseline Materialization

#### Root Cause
While `opposition_bowling_baselines.parquet` (206 rows) was generated during Step 4B, the reciprocal team batting baseline (`opposition_batting_baselines.parquet`) was not serialized into `contextual_baselines/`.

#### Remediation Implementation
Added query and Parquet writer in `generate_and_materialize_baselines()`:
```sql
SELECT 
    m.match_format,
    i.batting_team AS team_name,
    COUNT(DISTINCT m.match_id) AS total_matches,
    SUM(i.total_legal_deliveries) AS total_legal_deliveries,
    SUM(i.total_runs_scored) AS total_runs_scored,
    SUM(i.total_wickets_lost) AS total_wickets_lost,
    ROUND(SUM(i.total_runs_scored) * 6.0 / NULLIF(SUM(i.total_legal_deliveries), 0), 2) AS team_scoring_rate,
    ROUND(SUM(i.total_runs_scored) * 1.0 / NULLIF(SUM(i.total_wickets_lost), 0), 2) AS team_batting_average
FROM dim_match m
JOIN fact_innings i ON m.match_id = i.match_id
GROUP BY m.match_format, i.batting_team
ORDER BY m.match_format, total_matches DESC
```
Serialized to `data/datalake/feature_store/contextual_baselines/opposition_batting_baselines.parquet`.

#### Verification
- Output file exists and is readable via PyArrow.
- Exact row count: 206 format-team rows (matching the bowling unit baselines).
- Schema: `match_format`, `team_name`, `total_matches`, `total_legal_deliveries`, `total_runs_scored`, `total_wickets_lost`, `team_scoring_rate`, `team_batting_average`.

---

## 4. Feature Store Materialization & Partitioning Metrics

To prevent PyArrow `write_to_dataset` from appending duplicate files upon re-execution, an idempotent directory purge was introduced before materializing each dataset.

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
├── player_match/                            [200,709 rows, 46 cols, partitioned by match_format, season]
├── rolling_match/                           [602,127 rows, 34 cols, partitioned by match_format, window_size, season]
├── rolling_time/                            [602,127 rows, 19 cols, partitioned by match_format, window_days, season]
└── contextual_features/                     [200,709 rows, 18 cols, partitioned by match_format, season]
```

### Dataset Inventory

| Dataset | Record Count | Column Count | Partitioning Scheme | Materialization Time |
|---|---|---|---|---|
| `player_match` | 200,709 | 46 | `match_format`, `season` | 1.45 s |
| `rolling_match` (L5, L10, L20) | 602,127 | 34 | `match_format`, `window_size`, `season` | 13.70 s |
| `rolling_time` (30d, 90d, 365d) | 602,127 | 19 | `match_format`, `window_days`, `season` | 12.90 s |
| `contextual_features` | 200,709 | 18 | `match_format`, `season` | 5.08 s |
| `contextual_baselines` | 1,247 | Varies | Single Snappy Parquet files | 0.09 s |
| **Total Pipeline** | **1,606,919** | — | — | **34.17 s** |

---

## 5. Test Suite & Verification Results

The automated regression test suite was executed across all unit and integration test modules:

```bash
.venv/bin/pytest tests/
```

### Test Execution Summary
- **Tests Collected**: 54
- **Tests Passed**: 54
- **Tests Failed**: 0
- **Pass Rate**: 100.0%
- **Execution Time**: 2.37 seconds

### Breakdown of Test Coverage
- `tests/test_acquisition.py`: 11 passed (raw archive provenance, manifests, and checksum validation).
- `tests/test_data_leakage.py`: 4 passed (zero leakage, strictly preceding frames, and timeline invariance).
- `tests/test_environment.py`: 6 passed (Python, DuckDB, and PyArrow dependencies).
- `tests/test_feature_store.py`: 12 passed (schemas, row counts, zero-conflation, diamond ducks, caught-and-bowled, Test dismissals, canonical venues, and baselines).
- `tests/test_parser_schema.py`: 17 passed (parser entity integrity, relational constraints).
- `tests/test_rolling_features.py`: 4 passed (preceding window limits, time range limits, Bayesian shrinkage, multi-innings dismissals sum).

---

## 6. Files Modified During Step 4E

All modifications were confined strictly to configuration, feature store pipeline code, and tests:

1. [`config/canonical_venues.json`](file:///Users/divygupta/Desktop/DL_DATABASE/config/canonical_venues.json): 527 venue mappings to 500 canonical grounds with alias resolution.
2. [`etl/feature_definitions.py`](file:///Users/divygupta/Desktop/DL_DATABASE/etl/feature_definitions.py): Updated `PLAYER_MATCH_SCHEMA` (added `canonical_venue_name`, `dismissals_count`) and `CONTEXTUAL_FEATURES_SCHEMA` (added `canonical_venue_name`).
3. [`etl/rolling_features.py`](file:///Users/divygupta/Desktop/DL_DATABASE/etl/rolling_features.py): Updated rolling match and rolling time aggregations to sum `dismissals_count`.
4. [`etl/contextual_features.py`](file:///Users/divygupta/Desktop/DL_DATABASE/etl/contextual_features.py): Added `ensure_canonical_venues_loaded`, integrated canonical ground mapping, and partitioned expanding park factors by canonical ground.
5. [`etl/build_feature_store.py`](file:///Users/divygupta/Desktop/DL_DATABASE/etl/build_feature_store.py): Implemented diamond duck reconciliation, caught-and-bowled fielding credit, multi-innings dismissals count, canonical venue mapping, opposition batting baseline serialization, and idempotent partition directory cleaning.
6. [`tests/test_rolling_features.py`](file:///Users/divygupta/Desktop/DL_DATABASE/tests/test_rolling_features.py): Added `test_multi_innings_dismissals_in_rolling_average`.
7. [`tests/test_feature_store.py`](file:///Users/divygupta/Desktop/DL_DATABASE/tests/test_feature_store.py): Updated schema length and baseline row counts; added tests for all five remediation items.
8. [`docs/STEP_4E_REMEDIATION_REPORT.md`](file:///Users/divygupta/Desktop/DL_DATABASE/docs/STEP_4E_REMEDIATION_REPORT.md): This comprehensive verification report.

---

## 7. Final Recommendation & Readiness Gate

Phase 1: Step 4E Pipeline Remediation is **100% complete, fully verified, and ready for baseline freezing**.

- Zero production DuckDB data was altered (byte size and SHA-256 identical).
- Zero raw Cricsheet archives or manifests were modified.
- All 5 defects are completely resolved with mathematical and empirical correctness.
- All 54 automated regression tests pass with 100% success.
- Feature Store Parquet datasets have been regenerated deterministically.

We are ready to proceed to the next phase upon user authorization.
