# CricEngine AI — Phase 2: Dismissal and Fielding Fidelity Audit Report

**Date**: 2026-10-30  
**Phase**: Phase 2 — Comprehensive Data Quality and Relational Audit  
**Dimension**: Dismissal and Fielding Fidelity  
**Status**: AUDIT COMPLETE (Read-Only Inspection)  
**Database**: `data/datalake/curated/cricengine.duckdb` (Strictly Read-Only)  

---

## 1. Executive Summary

This audit evaluates dismissal classifications, bowler credit rules, caught-and-bowled attribution, multi-fielder relay coordination, and substitute fielder handling across all **136,691 dismissals** in `fact_delivery_dismissal` and **94,926 fielding credits** in `fact_dismissal_fielder`.

### Key Metrics Summary
- **Total Dismissals**: 136,691 (100% unique primary keys, 0 duplicates)
- **Dismissal Kinds Breakdown (14 distinct types)**:
  - `caught`: 79,585 (58.22%) — bowler credited
  - `bowled`: 26,076 (19.08%) — bowler credited
  - `lbw`: 14,133 (10.34%) — bowler credited
  - `run out`: 9,163 (6.70%) — uncredited to bowler
  - `caught and bowled`: 3,860 (2.82%) — bowler credited
  - `stumped`: 3,476 (2.54%) — bowler credited
  - `retired hurt`: 203 (0.15%) — uncredited to bowler
  - `hit wicket`: 139 (0.10%) — bowler credited
  - `retired out`: 31 (0.02%) — uncredited to bowler
  - `obstructing the field`: 15 (0.01%) — uncredited to bowler
  - `retired not out`: 7 (0.01%) — uncredited to bowler
  - `handled the ball`: 1 (<0.01%) — uncredited to bowler (historical rule)
  - `hit the ball twice`: 1 (<0.01%) — uncredited to bowler
  - `timed out`: 1 (<0.01%) — uncredited to bowler (Angelo Mathews, match 1384429)
- **Bowler Credit Distribution**:
  - **Bowler Credited**: 127,269 (93.11%)
  - **Uncredited (Run outs, Retirements, Infractions)**: 9,422 (6.89%)
  - **Credit Rule Compliance**: 136,691 / 136,691 (100.00% adherence to MCC Law 19–39)
- **Fielding Records (`fact_dismissal_fielder`)**:
  - Total records: 94,926 across 90,936 dismissals
  - Single-fielder dismissals: 87,039 (95.71%)
  - Multi-fielder dismissals: 3,897 (4.29%)
    - 2 fielders: 3,805 (relay catches, throw-and-break run outs)
    - 3 fielders: 91
    - 4 fielders: 1
- **Caught-and-Bowled**: 3,860 dismissals — dual attribution (bowler credit + fielder catch credit) confirmed 100% consistent following Step 4E remediation.
- **Substitute Fielders & Null References**:
  - `is_substitute = TRUE`: 2,423 records
  - Null `fielder_id` records: Exactly 15 rows (0.0158%) where substitute fielders were unnamed in Cricsheet raw JSON (`fielder_name_raw = ''`).

---

## 2. Dismissal & Fielding Data Model

```mermaid
erDiagram
    fact_ball_by_ball ||--o{ fact_delivery_dismissal : "produces"
    dim_player_master ||--o{ fact_delivery_dismissal : "dismisses"
    fact_delivery_dismissal ||--o{ fact_dismissal_fielder : "credited to"
    dim_player_master ||--o{ fact_dismissal_fielder : "fielded by"

    fact_delivery_dismissal {
        string dismissal_id PK "Composite key: ball_id || '_' || dismissal_seq"
        int64 match_id FK "References dim_match"
        string ball_id FK "References fact_ball_by_ball"
        string player_out_id FK "Dismissed batter (dim_player_master)"
        string player_out_name_raw "Scorecard name of batter"
        string dismissal_kind "caught, bowled, lbw, run out, etc."
        boolean bowler_credited "True if bowler credited with wicket"
    }

    fact_dismissal_fielder {
        string dismissal_fielder_id PK "dismissal_id || '_' || fielder_seq"
        string dismissal_id FK "References fact_delivery_dismissal"
        int16 fielder_seq "1, 2, 3, 4"
        string fielder_id FK "Nullable for unnamed subs (dim_player_master)"
        string fielder_name_raw "Raw name from scorecard"
        boolean is_substitute "True if 12th man / substitute fielder"
    }
```

---

## 3. Detailed Audit Findings

### Finding DF-01: Unnamed Substitute Fielder Records (LOW / DOCUMENTED SOURCE LIMITATION)
- **Affected Table**: `fact_dismissal_fielder`
- **Affected Records**: Exactly 15 records (0.0158% of fielding rows)
- **Description**: Exactly 15 rows in `fact_dismissal_fielder` possess `fielder_id IS NULL` and `fielder_name_raw = ''`, with `is_substitute = TRUE`.
- **Representative Examples**:
  - Match `1349386` (Inn 2, Over 1, Ball 5): `dismissal_fielder_id = 1349386_2_1_5_1_1`
  - Match `1424761` (Inn 2, Over 10, Ball 3): `dismissal_fielder_id = 1424761_2_10_3_1_1`
  - Match `1554537` (Inn 2, Over 15, Ball 3): `dismissal_fielder_id = 1554537_2_15_3_1_1`
- **Root Cause**: In Cricsheet's raw JSON delivery events, certain substitute fielders who took catches or effected run outs are specified as `{"fielders": [{"substitute": true}]}` without a `name` or `id` attribute.
- **Relational Impact**: Foreign key from `fact_dismissal_fielder.fielder_id` to `dim_player_master.player_id` is formally optional to accommodate unnamed substitutes. All 94,911 non-null `fielder_id`s strictly resolve to canonical players (0 broken foreign keys).
- **Status**: Formally accepted as a permanent source data limitation.

---

### Finding DF-02: Batting Dismissal Accounting for Non-Dismissal Retirements (MEDIUM / MODELING CONSIDERATION)
- **Affected Tables**: `fact_delivery_dismissal`, `data/datalake/feature_store/player_match/`
- **Affected Records**: 210 records (203 `retired hurt`, 7 `retired not out`)
- **Description**: Under official cricket rules (MCC Law 25.4), a batter who retires owing to injury or sickness (`retired hurt`) or retires with opposing consent (`retired not out`) is legally **not out**. Their score counts towards their career runs, but the innings does not count as a dismissal when computing batting average.
- **Audit Discovery**:
  - In `fact_delivery_dismissal`, these events are accurately labeled as `dismissal_kind = 'retired hurt'` and `bowler_credited = FALSE`.
  - In `etl/build_feature_store.py`, `dismissal_agg` groups all rows from `fact_delivery_dismissal` without filtering out `retired hurt` or `retired not out`.
  - Consequently, in `player_match`, 210 player appearances have `is_dismissed = TRUE` and `dismissals_count >= 1` despite being not out in official records.
- **Representative Example**:
  - Match `727927` (Pakistan vs Australia Test, 2014): Zulfiqar Babar retired hurt after scoring 7 runs. In `player_match`, he is recorded with `is_dismissed = TRUE`, `dismissals_count = 1`, `dismissal_kind = 'retired hurt'`.
- **Recommended Action for Phase 3**: In the Phase 3 feature store refinement, adjust `dismissal_agg` in `etl/build_feature_store.py` to exclude `retired hurt` and `retired not out` from `is_dismissed` and `dismissals_count`, while preserving `dismissal_kind` for provenance.

---

### Finding DF-03: Caught-and-Bowled Attribution Verification (POSITIVE VERIFICATION)
- **Affected Tables**: `fact_delivery_dismissal`, `fact_dismissal_fielder`, `player_match`
- **Affected Records**: 3,860 dismissals
- **Verification**:
  - In Step 4E remediation (Correction 2), the pipeline was updated to ensure that whenever `dismissal_kind = 'caught and bowled'`, the bowler receives credit as a fielder in `catches_taken`.
  - The audit confirmed that across all 3,860 caught-and-bowled dismissals:
    1. `bowler_credited = TRUE` in `fact_delivery_dismissal`.
    2. The bowler's canonical `player_id` is present in `fact_dismissal_fielder` with `fielder_seq = 1`.
    3. The bowler received exactly +1 catch credit in `player_match.catches_taken`.
- **Assessment**: Remediation verified with 100% accuracy.

---

### Finding DF-04: Multi-Fielder Relay Coordination Fidelity (POSITIVE VERIFICATION)
- **Affected Table**: `fact_dismissal_fielder`
- **Affected Records**: 3,897 dismissals (3,805 with 2 fielders, 91 with 3 fielders, 1 with 4 fielders)
- **Description**: Modern cricket features boundary relay catches and multi-throw run outs. The relational model stores each fielder participation as a separate sequenced row (`fielder_seq = 1, 2, 3...`).
- **Representative Example**:
  - Match `1384423` (IPL): Relay catch on the boundary rope where Fielder 1 caught the ball, threw it back inside the rope, and Fielder 2 completed the catch before grounding. Both fielders are recorded with their respective sequence numbers and canonical IDs.
- **Assessment**: Preserves complete fielding lineage without data truncation.

---

## 4. Quantitative Audit Summary

| Validation Check | Scope | Evaluated Rows | Passed | Violations / Exceptions | Pass Rate |
|:---|:---:|:---:|:---:|:---:|:---:|
| Dismissal PK Uniqueness | `fact_delivery_dismissal` | 136,691 | 136,691 | 0 | 100.00% |
| Ball Reference FK | `fact_delivery_dismissal` | 136,691 | 136,691 | 0 | 100.00% |
| Batter Reference FK | `fact_delivery_dismissal` | 136,691 | 136,691 | 0 | 100.00% |
| Bowler Credit Rule Compliance | `fact_delivery_dismissal` | 136,691 | 136,691 | 0 | 100.00% |
| Fielder PK Uniqueness | `fact_dismissal_fielder` | 94,926 | 94,926 | 0 | 100.00% |
| Fielder Dismissal FK | `fact_dismissal_fielder` | 94,926 | 94,926 | 0 | 100.00% |
| Fielder Player FK (Non-Null) | `fact_dismissal_fielder` | 94,911 | 94,911 | 0 | 100.00% |
| Unnamed Substitute Fielder Records | `fact_dismissal_fielder` | 15 | 15 | 15 (Expected NULL) | 100.00% |
| Caught-and-Bowled Dual Attribution | Both tables | 3,860 | 3,860 | 0 | 100.00% |

---

## 5. Audit Conclusion

The Dismissal and Fielding subsystem in `cricengine.duckdb` operates with **high fidelity**. All 14 dismissal kinds adhere strictly to official cricket scoring rules, caught-and-bowled dual attribution is completely verified, and the 15 null fielder IDs are proven to be legitimate representations of unnamed substitute fielders in Cricsheet raw JSON. A recommended refinement for Phase 3 is documented to handle `retired hurt` in batting average calculations.
