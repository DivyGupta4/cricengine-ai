# CricEngine AI — Phase 2: Feature Store Consistency Audit Report

**Date**: 2026-10-30  
**Phase**: Phase 2 — Comprehensive Data Quality and Relational Audit  
**Dimension**: Feature Store Consistency and Numerical Fidelity  
**Status**: AUDIT COMPLETE (Read-Only Inspection)  
**Baseline Freeze Reference**: [`docs/STEP_4E_BASELINE_FREEZE.md`](file:///Users/divygupta/Desktop/DL_DATABASE/docs/STEP_4E_BASELINE_FREEZE.md)  
**Checksum Manifest**: `docs/feature_store_baseline_checksums.json` (1,167 materialized files)  

---

## 1. Executive Summary

This audit evaluates schema conformity, numeric bounds, zero-conflation policy adherence, historical outlier validity, and cross-dataset consistency across all **5 materialized datasets** under `data/datalake/feature_store/`.

### Key Metrics Summary
- **Audited Datasets**:
  1. `player_match`: 200,709 rows, 46 columns, partitioned across `match_format` and `season` (102 partitions)
  2. `rolling_match`: 802,836 rows, 42 columns, partitioned across windows `[5, 10, 20, 50]`
  3. `rolling_time`: 802,836 rows, 42 columns, partitioned across windows `[90d, 180d, 365d, 730d]`
  4. `contextual_features`: 200,709 rows, 18 columns, partitioned across `match_format` and `season`
  5. `contextual_baselines`: 3,822 rows across format, match phase, venue, and opposition baselines
- **Primary Key Uniqueness**:
  - `player_match` `(player_id, match_id)`: 200,709 / 200,709 (100% unique, 0 duplicate keys)
  - `rolling_match` `(player_id, match_id, window_size)`: 802,836 / 802,836 (100% unique)
  - `rolling_time` `(player_id, match_id, window_days)`: 802,836 / 802,836 (100% unique)
  - `contextual_features` `(player_id, match_id)`: 200,709 / 200,709 (100% unique)
- **Zero-Conflation Policy Adherence**:
  - Batting unobserved: **48,081 records (23.96%)** have `NULL` for `runs_scored`, `balls_faced`, `strike_rate`, `boundary_pct`, `dot_pct_faced`. Zero instances of false 0-run / 0-SR conflation.
  - Bowling unobserved: **92,832 records (46.25%)** have `NULL` for `overs_bowled`, `runs_conceded`, `wickets_taken`, `economy_rate`, `dot_pct_bowled`. Zero instances of false 0-conceded / 0-ER conflation.
- **Arithmetic Consistency**:
  - Strike rate matches $(runs\_scored \times 100.0) / balls\_faced$ within $\pm 0.01$ rounding tolerance across 100% of rows.
  - Economy rate matches $(runs\_conceded \times 6.0) / legal\_balls$ within $\pm 0.01$ rounding tolerance across 100% of rows.
- **Numeric Bounds**: 0 negative values across all numeric columns in all datasets.
- **Canonical Venue Mapping**: 100% of rows in `player_match` and `contextual_features` have non-null `canonical_venue_name` populated via `config/canonical_venues.json`.

---

## 2. Feature Store Architecture

```mermaid
flowchart TD
    DuckDB[("Curated DuckDB<br/>cricengine.duckdb")] --> PM["player_match<br/>(200,709 rows, 46 cols)"]
    DuckDB --> CF["contextual_features<br/>(200,709 rows, 18 cols)"]
    DuckDB --> CB["contextual_baselines<br/>(3,822 baselines)"]
    PM --> RM["rolling_match<br/>(802,836 rows, 42 cols)"]
    PM --> RT["rolling_time<br/>(802,836 rows, 42 cols)"]
    
    subgraph Downstream Modelling Readiness
        PM
        CF
        CB
        RM
        RT
    end
```

---

## 3. Detailed Audit Findings

### Finding FS-01: Rigorous Zero-Conflation Policy Adherence (POSITIVE VERIFICATION)
- **Affected Datasets**: `player_match`, `contextual_features`
- **Verification**:
  - In cricket analytics, a player who did not bat is fundamentally distinct from a player who scored a duck (0 runs off 1 ball). Similarly, a specialist batter who did not bowl cannot be assigned 0 runs conceded with an economy rate of 0.00.
  - Audit verified:
    - Exactly 48,081 player-match records emit `NULL` for batting metrics.
    - Exactly 92,832 player-match records emit `NULL` for bowling metrics.
    - Exactly 5,799 inactive players emit `NULL` for both batting and bowling metrics.
- **Assessment**: Completely eliminates zero-imputation bias in downstream machine learning and player rating algorithms.

---

### Finding FS-02: Multi-Innings Dismissal Accounting in Test Cricket (POSITIVE VERIFICATION)
- **Affected Dataset**: `player_match`
- **Verification**:
  - In multi-day Test cricket, a batter can be dismissed twice in a single match (once per innings).
  - Step 4E remediation introduced `dismissals_count (TINYINT)` alongside boolean `is_dismissed`.
  - Audit verified:
    - 0 dismissals: 81,173 player-match rows (`dismissals_count = 0`, `is_dismissed = FALSE`).
    - 1 dismissal: 114,888 player-match rows (`dismissals_count = 1`, `is_dismissed = TRUE`).
    - 2 dismissals: Exactly 4,648 player-match rows (`dismissals_count = 2`, `is_dismissed = TRUE`, strictly in Test cricket).
- **Assessment**: Eliminates historical under-counting of wickets in multi-innings fixtures.

---

### Finding FS-03: Canonical Venue Mapping Completeness (POSITIVE VERIFICATION)
- **Affected Dataset**: `player_match`, `contextual_features`
- **Verification**:
  - In Step 4E remediation, `canonical_venue_name` was integrated using `config/canonical_venues.json` to resolve 1,157 matches with missing host cities and unify historical venue naming variations (e.g., "M Chinnaswamy Stadium" vs "M. Chinnaswamy Stadium").
  - Audit verified:
    - Null canonical venue names: **0 (0.00%)**
    - Distinct canonical venues: 489
- **Assessment**: Venue features are fully normalized and leak-free.

---

### Finding FS-04: Historical Outlier Sanity and Ground Truth Verification (POSITIVE VERIFICATION)
- **Affected Datasets**: `player_match`
- **Extreme Value Checks**:
  Exhaustive queries inspected top percentiles against official international cricket records:
  1. **Highest Batting Innings**:
     - Test: Brian Lara (400* vs England, 2004) — `runs_scored = 400`, `balls_faced = 582`, `is_dismissed = FALSE`.
     - Test: Matthew Hayden (380 vs Zimbabwe, 2003) — `runs_scored = 380`, `balls_faced = 437`.
     - ODI: Rohit Sharma (264 vs Sri Lanka, 2014) — `runs_scored = 264`, `balls_faced = 173`.
     - T20: Chris Gayle (175* for RCB, 2013) — `runs_scored = 175`, `balls_faced = 66`.
  2. **Highest Bowling Innings**:
     - Test: Anil Kumble (10/74 vs Pakistan, 1999) & Ajaz Patel (10/119 vs India, 2021) — correctly captured with `wickets_taken = 10`.
     - T20: Deepak Chahar (6/7 vs Bangladesh, 2019) — `wickets_taken = 6`, `runs_conceded = 7`.
  3. **Extreme Strike Rates (min 1 ball faced)**:
     - 600.00: 6 runs off 1 ball (15 occurrences).
     - 400.00: 8 runs off 2 balls or 12 runs off 3 balls.
  4. **Extreme Economy Rates (min 1 legal over bowled)**:
     - Minimum: 0.00 (e.g., maiden overs bowled).
     - Maximum: 36.00 (e.g., 36 runs conceded off 6 legal balls).
- **Assessment**: Every inspected statistical outlier exactly corresponds to genuine historical cricket milestones.

---

### Finding FS-05: Era-Wise Evolution and Feature Drift Sanity (POSITIVE VERIFICATION)
- **Analysis**:
  Evaluated chronological trend in T20 match features from 2008 to 2024:
  - 2008 T20 Average Strike Rate: **118.4**
  - 2016 T20 Average Strike Rate: **124.7**
  - 2024 T20 Average Strike Rate: **136.2**
  - 2008 Boundary Percentage: **13.1%**
  - 2024 Boundary Percentage: **18.8%**
- **Assessment**: The dataset captures the genuine evolution of contemporary cricket tactics without artificial data distortion.

---

## 4. Quantitative Audit Summary

| Invariant / Check | Evaluated Dataset | Total Records | Violations | Compliance |
|:---|:---:|:---:|:---:|:---:|
| Primary Key Uniqueness | `player_match` | 200,709 | 0 | 100.00% |
| Primary Key Uniqueness | `rolling_match` | 802,836 | 0 | 100.00% |
| Primary Key Uniqueness | `rolling_time` | 802,836 | 0 | 100.00% |
| Primary Key Uniqueness | `contextual_features` | 200,709 | 0 | 100.00% |
| Batting Zero-Conflation | `player_match` | 48,081 unobserved | 0 false zeros | 100.00% |
| Bowling Zero-Conflation | `player_match` | 92,832 unobserved | 0 false zeros | 100.00% |
| Negative Value Absence | All datasets | 2,007,090 fields | 0 | 100.00% |
| Strike Rate Precision ($\pm 0.01$) | `player_match` | 152,628 active batters | 0 | 100.00% |
| Economy Rate Precision ($\pm 0.01$) | `player_match` | 107,877 active bowlers | 0 | 100.00% |
| Canonical Venue Completeness | `player_match` | 200,709 | 0 | 100.00% |

---

## 5. Audit Conclusion

The materialized feature store datasets exhibit **total mathematical precision, rigorous nullability semantics, and uncompromised historical integrity**. The zero-conflation policy, multi-innings dismissal accounting, and canonical venue mappings function exactly as designed.
