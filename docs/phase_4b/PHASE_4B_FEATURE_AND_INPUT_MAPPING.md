# Phase 4B — Feature & Input Mapping Specification

> **Authority**: Phase 4B Milestone Implementation  
> **Status**: COMPLETED, AUDITED, AND PRODUCTION READY  
> **Target Module**: `src/ratings/`  
> **Lead Roles**: Lead ML Systems Architect, Senior Data Engineer  

---

## 1. Input Source Governance & Provenance

The rating engine is strictly read-only and consumes data exclusively from the approved, frozen Phase 3B.1 baselines:
- **Canonical DuckDB Database**: `data/datalake/curated/cricengine.duckdb` (401,616,896 bytes, SHA-256 `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae`).
- **Approved Feature Store v3b**: `data/datalake/feature_store_v3b/` (Version `3.1.0-phase3b`, 1,167 files).

---

## 2. Relational & Columnar Feature Mapping Matrix

The following table documents the exact physical mapping from the underlying data lake tables into the rating engine state-space updates:

| Physical Source Table / Dataset | Source Column Name | Target Engine Variable | Data Type | Physical Interpretation & Application |
| :--- | :--- | :--- | :--- | :--- |
| `player_match` | `player_id` | `player_id` | `VARCHAR(8)` | Canonical 8-character hex player identifier. |
| `player_match` | `match_id` | `match_id` | `VARCHAR(32)` | Unique match identifier. |
| `player_match` | `start_date` | `batch_date` | `DATE` / `VARCHAR` | Calendar date establishing chronological batch boundaries. |
| `player_match` | `match_format` | `match_format` | `VARCHAR(8)` | Evaluated format: `T20`, `ODI`, `TEST`. |
| `player_match` | `runs_scored` | `runs_scored` | `INTEGER` | Batting Negative-Binomial count observation $R_i$. |
| `player_match` | `balls_faced` | `balls_faced` | `INTEGER` | Physical exposure denominator $B_i$ for batting rate and survival. |
| `player_match` | `is_dismissed` | `is_dismissed` | `BOOLEAN` | In-match dismissal indicator $D_i$ for Bernoulli survival process. |
| `player_match` | `legal_balls_bowled` | `legal_balls_bowled`| `INTEGER` | Physical exposure denominator $L_j$ for bowling hazard and economy. |
| `player_match` | `runs_conceded` | `runs_conceded` | `INTEGER` | Bowling Negative-Binomial count observation $R_{c, j}$. |
| `player_match` | `wickets_credited` | `wickets_credited` | `INTEGER` | Bowling Negative-Binomial hazard count observation $W_j$. |
| `player_match` | `catches_taken` | `catches_taken` | `INTEGER` | Outfield catching observation $C_i$ (defaults to 0 if NULL). |
| `player_match` | `runouts_involved` | `runouts_involved` | `INTEGER` | Direct run-out involvements (weighted at 1.5x in ZIP). |
| `player_match` | `in_starting_xi` | `in_starting_xi` | `BOOLEAN` | Fielding exposure gate (exposure = 0 if not starting XI). |
| `player_match` | `batting_load` | `batting_load` | `DOUBLE` | Innings resource consumption share for additive all-round value. |
| `player_match` | `bowling_load` | `bowling_load` | `DOUBLE` | Overs share delivered for additive all-round value. |
| `player_match` | `batting_position` | `batting_position` | `INTEGER` | Rolling history feature for Dynamic Role Inference ($\text{DPI-RI}$). |
| `player_match` | `overs_bowled` | `overs_bowled` | `DOUBLE` | Rolling workload feature for Dynamic Role Inference ($\text{DPI-RI}$). |
| `player_match` | `stumpings_taken` | `stumpings_taken` | `INTEGER` | Wicketkeeper detection indicator ($\text{DPI-RI}$). |
| `player_match` | `pace_spin_class` | `pace_spin_class` | `VARCHAR` | Pace vs Spin disciplinary categorization ($\text{DPI-RI}$). |
| `contextual_features` | `venue_historical_park_factor` | `raw_pf` | `DOUBLE` | Venue run-scoring park factor baseline. |
| `contextual_features` | `opposition_bowling_quality_index`| `obq` | `DOUBLE` | $I_{\text{OBQ}}$: Divides expected batting runs. |
| `contextual_features` | `opposition_batting_quality_index`| `bat_q` | `DOUBLE` | $I_{\text{BatQuality}}$: Multiplies bowling runs conceded; divides wickets. |
| `contextual_baselines` | `venue_park_factors.parquet` | `park_factor` | `DOUBLE` | Pre-match baseline shrunk via Empirical Bayes ($K=10$). |
| `player_source_identity`| `confidence_status` | `identity_status`| `VARCHAR` | Mapped to mixture weight $w_{\text{id}}$ (0.65 for `c65e0275`). |

---

## 3. Excluded & Banned Features (Zero-Leakage Safeguards)

| Excluded Feature Name | Physical Location | Reason for Exclusion & Mathematical Risk | Approved Alternative Treatment |
| :--- | :--- | :--- | :--- |
| `primary_role` | `player_match` | **STATIC CAREER LABEL (LOOKAHEAD BIAS)**: Assigns future career achievements retrospectively. | **BANNED**. Replaced by Dynamic Point-in-Time Role Inference ($\text{DPI-RI}$) from pre-match history. |
| `player_age_at_match` | `player_match` | **92.5% NULL (MISSINGNESS HAZARD)**: Date of birth missing for 185,782 records. | **BANNED**. Replaced by calendar inactivity drift ($\mathbf{Q}\Delta t$) and form residuals. |
| `WRF` (Wicket Rate Factor) | Hypothesized in 4A | **NON-EXISTENT IN DATABASE**: Fictitious column not present in Feature Store v3b. | **PURGED**. Derived analytically from $F_{\text{venue}}^{-0.45}$. |
| `SPR` (Spin-to-Pace Ratio) | Hypothesized in 4A | **NON-EXISTENT IN DATABASE**: Fictitious column not present in Feature Store v3b. | **PURGED**. Inferred dynamically from opposition spinner workload. |
| `allrounder_balance_index` | `player_match` | In-match realization contains contemporaneous game-state load. | Replaced by `mean_allrounder_index` from pre-match rolling windows. |

---

## 4. Exposure & Data Cleaning Logic

### 4.1. Batting Exposure Handling
- If `balls_faced == 0`: The player did not bat (DNB). Batting state retains prior mean and variance without update ($\Delta \boldsymbol{\theta}_{\text{bat}} = 0$).
- If `balls_faced > 0` and `runs_scored == 0`: Player scored a duck or was not out on 0. This is a completely valid Negative-Binomial observation that cleanly updates the scoring rate downward.

### 4.2. Bowling Exposure Handling
- If `legal_balls_bowled == 0`: The player did not bowl. Bowling state undergoes pure time-drift without observation update.
- If `legal_balls_bowled > 0` and `wickets_credited == 0`: Wicketless spell. Fully valid Negative-Binomial observation updating hazard rate downward.

### 4.3. Fielding Exposure Handling
- If `in_starting_xi == False` or unverified: Exposure is set to $0.0$.
- If `in_starting_xi == True`: Exposure is set to standard team deliveries fielded ($120$ in T20, $300$ in ODI, $450$ in Test).

---

> **Mapping Sign-Off**: All physical inputs map directly to verified, materialized columns in `cricengine.duckdb` and `feature_store_v3b/`. Static labels and heavily missing attributes have been completely eliminated.
