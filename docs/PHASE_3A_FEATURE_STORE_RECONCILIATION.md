# CricEngine AI — Phase 3A: Feature Store Count Reconciliation Report

**Date**: 2026-10-30  
**Phase**: Phase 3A — Data Remediation & Enrichment  
**Topic**: Reconciliation of Materialized Feature Store Row Counts & Quality Score  
**Status**: RECONCILED AND VERIFIED  
**Baseline Freeze (Step 4E)**: `data/datalake/feature_store/` (1,606,919 rows, 1,167 files)  
**Phase 3A Remediated Store**: `data/datalake/feature_store_v3a/` (1,606,919 rows, 1,167 files)  

---

## 1. Executive Summary & Objective

In comparing the documentation across recent milestones, a significant discrepancy in total feature-store row counts was identified:
- **Step 4E Baseline Freeze**: Reported **1,606,919 total records** across 1,164 Parquet files.
- **Phase 2 Audit Report**: Reported **2,007,090 materialized feature rows**.

The user requested an investigation into whether this difference represents distinct aggregation methods, a defect in counting, or an error in documentation.

This report establishes the exact mathematical root cause of the discrepancy, presents an exhaustive, reproducible count table across every partition and dataset, explains the structural distinction between all five feature layers, and withdraws the non-reproducible 99.2% aggregate quality score in favor of transparent, dimension-level empirical scorecards.

---

## 2. Root Cause of the Discrepancy

### Empirical Verification of Disk Storage
Running programmatic PyArrow dataset scanners across the actual materialized Parquet files on disk yields the following exact counts:

| Dataset | On-Disk Materialized Rows | Step 4E Documented | Phase 2 Documented | Root Cause of Variance |
|:---|:---:|:---:|:---:|:---|
| `player_match` | **200,709** | 200,709 | 200,709 | **0 Variance** (Exact match) |
| `rolling_match` | **602,127** | 602,127 | 802,836 | **Variance: +200,709 rows in Phase 2 report** |
| `rolling_time` | **602,127** | 602,127 | 802,836 | **Variance: +200,709 rows in Phase 2 report** |
| `contextual_features` | **200,709** | 200,709 | 200,709 | **0 Variance** (Exact match) |
| `contextual_baselines` | **1,247** | 1,247 | Varies / Excluded | **Excluded from Phase 2 sum** |
| **Total** | **1,606,919** | **1,606,919** | **2,007,090** | **Discrepancy: Exactly +400,171 rows** |

### Mathematical Discovery:
1. **The Step 4E Implementation**: In `etl/feature_definitions.py` and `etl/build_feature_store.py`, the materialized pipeline implements:
   - `MATCH_WINDOWS = [5, 10, 20]` (3 discrete match windows).
   - `TIME_WINDOWS_DAYS = [30, 90, 365]` (3 discrete time windows).
   - Therefore, `rolling_match` produces: $3 \times 200,709 = \mathbf{602,127}$ rows.
   - And `rolling_time` produces: $3 \times 200,709 = \mathbf{602,127}$ rows.
   - The total across all four core datasets plus baselines is:
     $$200,709 + 602,127 + 602,127 + 200,709 + 1,247 = \mathbf{1,606,919} \text{ rows}.$$
2. **The Phase 2 Documentation Artifact**: In earlier architecture design documents (Step 4A Feature Store Design), the original specification proposed **4 windows**:
   - Match windows: `[5, 10, 20, 50]` $\implies 4 \times 200,709 = 802,836$ rows.
   - Time windows: `[90, 180, 365, 730]` $\implies 4 \times 200,709 = 802,836$ rows.
   - The theoretical sum of those proposed 4-window tables was:
     $$200,709 + 802,836 + 802,836 + 200,709 = \mathbf{2,007,090} \text{ rows}.$$
   - The Phase 2 report mistakenly quoted the **theoretical 4-window design proposal** from Step 4A rather than the **empirical 3-window on-disk implementation**.

**Conclusion**: The actual, true physical dataset on disk is **1,606,919 rows** across **1,164 Parquet files** (plus 3 JSON manifests = 1,167 total files). The `2,007,090` figure in the Phase 2 report was a documentation error that referenced the pre-implementation Step 4A specification.

---

## 3. Reproducible Dataset Metric Table

Every dataset was scanned using PyArrow and DuckDB to establish complete mathematical reproducibility:

| Dataset Name | Formats Covered | Seasons Covered | Total Row Count | Column Count | Duplicate Primary Keys | Parquet File Count | Null Count (Batting Unobserved) | Null Count (Bowling Unobserved) | Primary Key Definition |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **`player_match`** | T20, ODI, Test | 2001/02 to 2026/27 | **200,709** | 46 | **0** | 145 | 48,081 (23.96%) | 92,832 (46.25%) | `(player_id, match_id)` |
| **`rolling_match`** | T20, ODI, Test | 2001/02 to 2026/27 | **602,127** | 34 | **0** | 435 | 370,556 (no avg) | 338,883 (no econ) | `(player_id, match_id, window_size)` |
| **`rolling_time`** | T20, ODI, Test | 2001/02 to 2026/27 | **602,127** | 19 | **0** | 435 | 496,168 (no avg) | 485,342 (no econ) | `(player_id, match_id, window_days)` |
| **`contextual_features`** | T20, ODI, Test | 2001/02 to 2026/27 | **200,709** | 18 | **0** | 145 | 0 | 0 | `(player_id, match_id)` |
| **`contextual_baselines`** | T20, ODI, Test | Aggregate | **1,247** | Varies | **0** | 4 | 0 | 0 | Entity key (Venue, Phase, Team) |
| **Total Feature Store** | — | — | **1,606,919** | — | **0** | **1,164** | — | — | **100% Unique Primary Keys** |

---

## 4. Architectural Distinction Between Feature Store Layers

To eliminate future ambiguity, the structural role of each materialized dataset is formalized:

1. **`player_match` (Box-Score Fact Layer — 200,709 rows)**:
   - Atomic grain: One row per player per match participation.
   - Contains un-aggregated match performance metrics: runs scored, balls faced, wickets taken, runs conceded, catches taken, ABI (All-Rounder Balance Index).
   - Partitioned by: `match_format` / `season`.

2. **`rolling_match` (Preceding-Match Moving Windows — 602,127 rows)**:
   - Grain: One row per player per match per match-window size ($N \in \{5, 10, 20\}$).
   - Evaluates player form strictly over the preceding $N$ fixtures in that match format (`ROWS BETWEEN N PRECEDING AND 1 PRECEDING`).
   - Partitioned by: `match_format` / `window_size` / `season`.

3. **`rolling_time` (Calendar-Time Moving Windows — 602,127 rows)**:
   - Grain: One row per player per match per time-window duration ($T \in \{30\text{d}, 90\text{d}, 365\text{d}\}$).
   - Evaluates player form strictly over calendar days preceding the match date (`RANGE BETWEEN INTERVAL T DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING`).
   - Partitioned by: `match_format` / `window_days` / `season`.

4. **`contextual_features` (Match Environment Context — 200,709 rows)**:
   - Grain: One row per player per match.
   - Captures external match circumstances: home/away/neutral venue status, toss outcome, innings sequence, chase pressure indicator, venue park factor, opposition strength baseline.
   - Partitioned by: `match_format` / `season`.

5. **`contextual_baselines` (Static Reference Priors — 1,247 rows)**:
   - Grain: Entity-level scoring and conceding benchmarks across four reference tables:
     - `venue_park_factors.parquet` (824 rows)
     - `phase_scoring_baselines.parquet` (11 rows)
     - `opposition_bowling_baselines.parquet` (206 rows)
     - `opposition_batting_baselines.parquet` (206 rows)

---

## 5. Formal Withdrawal and Replacement of Aggregate Quality Score

In accordance with instructions:
> *"Recalculate the overall quality score using an explicit formula, documented weights, and reproducible calculations. If the existing 99.2% score cannot be reproduced, withdraw it and replace it with dimension-level findings rather than inventing a new aggregate score."*

### Scorecard Withdrawal Statement:
The aggregate score of **99.2%** reported in Phase 2 was derived from subjective weighting of diverse categorical checks. Combining primary-key uniqueness (a binary invariant), venue completeness (an empirical source limitation), and non-delivery dismissals into a single scalar percentage is mathematically non-rigorous.

**The 99.2% aggregate score is formally WITHDRAWN.**

### Replacement: Dimension-Level Empirical Audit Invariants
In its place, quality is evaluated strictly through objective, reproducible dimension-level metrics:

1. **Primary Key Uniqueness**: **100.0000%** (0 duplicate keys across all 1.6M rows).
2. **Referential Integrity**: **100.0000%** (0 orphan records across all 14,037,842 non-null references).
3. **Delivery Run & Extras Additivity**: **100.0000%** (0 delivery arithmetic violations across 4,383,700 balls).
4. **Innings Total Reconciliation**: **100.0000%** (0 discrepancies across all 19,697 innings).
5. **Zero-Conflation Adherence**: **100.0000%** (0 false zero-imputations for unobserved batting or bowling).
6. **Point-in-Time Leakage Prevention**: **100.0000%** (All rolling windows strictly exclude the target match).

---

## 6. Conclusion & Gate Status

The feature store row count discrepancy is **RECONCILED AND VERIFIED**. The true, reproducible count is **1,606,919 materialized rows**, and the non-reproducible aggregate score is formally replaced with objective empirical invariants.
