---
license: cc-by-sa-4.0
tags:
- sports-analytics
- cricket
- bayesian-modeling
- feature-store
- time-series
- valuation
size_categories:
- 1M<n<10M
---

# Dataset Card for CricEngine AI Dataset

## 1. Dataset Summary

The **CricEngine AI Dataset** is a comprehensive, open-access, point-in-time cricket analytics and predictive data lake. It provides normalized ball-by-ball match data, rolling multi-window feature stores, Bayesian latent skill ratings, probabilistic forecast distributions, and Value Over Replacement Player (VORP) metrics across all major men's professional cricket competitions.

- **Primary Source:** Cricsheet (https://cricsheet.org)
- **Time Coverage:** 2002 – 2026
- **Match Formats:** Test Matches, One-Day Internationals (ODIs), T20 Internationals (T20Is), Indian Premier League (IPL), and Syed Mushtaq Ali Trophy (SMAT).
- **Match Count:** 9,085 matches (4.38+ million deliveries).
- **Release Version:** `v1.0.0` (Immutable approved data state).

---

## 2. Dataset Structure & Components

The dataset is partitioned into four decoupled, versioned tiers:

### A. Canonical DuckDB Relational Database (`cricengine.duckdb`)
- **Format:** DuckDB Columnar Relational File (.duckdb v2.0.0)
- **Size:** 383 MB (401,616,896 bytes)
- **SHA-256:** `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae`
- **Total Tables:** 14 relational tables in Third Normal Form (3NF).
- **Total Rows:** 4,907,393 rows.
- **Key Tables:** `dim_match`, `dim_match_context`, `dim_player_master`, `fact_innings`, `fact_ball_by_ball`, `fact_match_participation`, `fact_delivery_dismissal`, `fact_dismissal_fielder`.

### B. Feature Store (`feature_store_v3b`)
- **Format:** Apache Parquet (Snappy compressed, Hive partitioned).
- **Files:** 1,164 files (~117 MB).
- **Total Records:** 1,605,672 rows.
- **Subsets:**
  - `player_match`: 200,709 rows (51 columns) of match-level performance metrics.
  - `rolling_match`: 602,127 rows (34 columns) across 5, 10, and 20-match moving windows with exponential decay and empirical shrinkage.
  - `rolling_time`: 602,127 rows (19 columns) across 30, 90, and 365 calendar-day windows.
  - `contextual_features`: 200,709 rows (18 columns) of venue park factors and opponent quality indices.
  - `contextual_baselines`: Reference tables for park factors and phase baselines.

### C. Player Rating Store (`rating_store_v4`)
- **Format:** Apache Parquet (Hive partitioned by format).
- **Files:** 145 files (12.5 MB).
- **Model:** Context-Aware Hierarchical Bayesian State-Space (CA-HBSS).
- **Subsets:**
  - `pre_match_snapshots`: 19,642 pre-match snapshots (**D-1 guarantee** strictly frozen prior to match start).
  - `player_rating_current`: 9,406 active format states across batting, bowling, fielding, and all-round composite roles.
  - `player_rating_history`: 73,039 longitudinal rating progression checkpoints.

### D. Predictive Store (`predictive_store_v4c`)
- **Format:** Apache Parquet (Hive partitioned by format and year).
- **Files:** 86 files (2.8 MB).
- **Model:** Two-Stage Hurdle / Zero-Inflated Poisson & Value Over Replacement Player (VORP).
- **Subsets:**
  - `player_match_vorp`: 9,708 rows evaluating match contribution against replacement level (Surplus ratio: 0.997).
  - `batting_predictions`: 9,708 rows of forecasted runs with 50%, 80%, 90%, 95% intervals.
  - `bowling_predictions`: 9,708 rows of forecasted wickets and runs conceded.
  - `fielding_predictions`: 9,708 rows of expected fielding run values.
  - `evaluation_metrics`: Calibration diagnostics and benchmark comparisons.

---

## 3. Intended Uses

### In-Scope Uses
- Quantitative cricket analytics research and econometric modeling.
- Point-in-time machine learning feature engineering benchmarks without lookahead bias.
- Bayesian dynamic rating system validation and state-space estimation.
- Empirical valuation of player marginal utility in limited-overs and multi-day cricket.
- Reproducible academic demonstration and coursework in data engineering.

### Out-of-Scope & Prohibited Uses
- Live, in-play sports betting, gambling syndicates, or real-time odds calculation.
- Commercial automated contract negotiations without contextual human audit.
- Treating predictive outputs as guarantees of future sporting performance.

---

## 4. Data Collection, Ingestion & Quality

All underlying match data is sourced from **Cricsheet** (https://cricsheet.org). Cricsheet compiles ball-by-ball match scorecards published by cricket governing bodies and major sports broadcasters.

### Ingestion Pipeline
1. **Raw Retrieval:** ZIP archives (`tests_male_json.zip`, `odis_male_json.zip`, `t20s_male_json.zip`, `ipl_male_json.zip`, `sma_male_json.zip`) are downloaded and verified against cryptographic SHA-256 manifests.
2. **Quarantine Gate:** JSON files are strictly schema-validated. Any malformed files missing core delivery structures are moved to `data/quarantine/`.
3. **Canonical Normalization:** Deeply nested JSON arrays are parsed into normalized Third Normal Form (3NF) relational tables in DuckDB.
4. **Identity Disambiguation:** 7,029 source player strings are linked to canonical player identifiers in `dim_player_master` using cross-referenced registry tokens with 99.98% verified confidence.

---

## 5. Known Biases and Limitations

1. **Domestic Tournament Coverage:** Cricsheet provides complete coverage for the Indian Senior T20 domestic championship (**Syed Mushtaq Ali Trophy**), but does **not** provide ball-by-ball structured data for Indian First-Class (**Ranji Trophy**) or List-A (**Vijay Hazare Trophy**) competitions.
2. **Optical Tracking Data Absence:** The dataset does not contain optical tracking coordinates (e.g., Hawkeye pitch trajectory, ball release velocity, swing deviation, or fielder GPS movement).
3. **Associate T20I Sample Sizes:** Lower-tier international matches often feature small sample sizes and higher variance in opposing team quality.
4. **Historical Completeness:** Comprehensive ball-by-ball data coverage begins around 2002 for international cricket and 2008 for franchise T20 leagues. Earlier historical eras are not represented.

---

## 6. Licensing and Attribution

This dataset is distributed under the terms of open data licenses:
- **Database Licensing:** The derived database and tabular files are governed by the **Open Data Commons Open Database License (ODbL) v1.0** (https://opendatacommons.org/licenses/odbl/1.0/).
- **Match Records Licensing:** Underlying delivery records are licensed under **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)** (https://creativecommons.org/licenses/by-sa/4.0/).
- **Attribution:** Data provided courtesy of **Cricsheet** (https://cricsheet.org), maintained by Stephen Rushe.
- **Source Code:** Software tools and download utilities are licensed under the **MIT License**.
