# Phase 4B — Rating Store Schema & Storage Architecture

> **Authority**: Phase 4B Milestone Implementation  
> **Status**: COMPLETED, MATERIALIZED, AND VERIFIED  
> **Target Storage**: `data/datalake/rating_store_v4/`  
> **Lead Roles**: Lead ML Systems Architect, Senior Data Engineer  

---

## 1. Physical Topology & Directory Layout

The rating store is materialized as columnar Apache Parquet datasets partitioned using standard Hive directory structures with Snappy compression:

```
data/datalake/rating_store_v4/
├── _manifest.json
├── audit_records/
│   └── audit_log.json
├── player_rating_current/
│   ├── match_format=ODI/
│   │   └── current_ratings.parquet
│   ├── match_format=T20/
│   │   └── current_ratings.parquet
│   └── match_format=TEST/
│       └── current_ratings.parquet
├── player_rating_history/
│   ├── match_format=ODI/
│   │   ├── year=2002/history.parquet
│   │   └── ...
│   ├── match_format=T20/
│   │   ├── year=2005/history.parquet
│   │   └── ...
│   └── match_format=TEST/
│       ├── year=2001/history.parquet
│       └── ...
└── pre_match_snapshots/
    ├── match_format=ODI/
    ├── match_format=T20/
    └── match_format=TEST/
```

---

## 2. Table Schema Specifications

### 2.1. `player_rating_current`
Contains the latest, most up-to-date rating state for every player in each format:
- **Partitioning**: Hive partition `match_format=...` (`ODI`, `T20`, `TEST`).
- **File Name**: `current_ratings.parquet`.

| Field Name | Physical Type | Nullable | Description / Analytical Invariant |
| :--- | :--- | :---: | :--- |
| `player_id` | `STRING` | NO | Canonical 8-character hex player identifier. |
| `as_of_date` | `STRING` | NO | Date of last state evaluation (`YYYY-MM-DD`). |
| `last_match_date` | `STRING` | YES | Date of last competitive match played. |
| `observations_count` | `INT64` | NO | Cumulative match appearances evaluated. |
| `effective_exposure_bat` | `FLOAT64` | NO | Cumulative balls faced exposure. |
| `effective_exposure_bowl`| `FLOAT64` | NO | Cumulative legal balls bowled exposure. |
| `effective_exposure_field`| `FLOAT64` | NO | Cumulative team deliveries fielded exposure. |
| `theta_bat_rate` | `FLOAT64` | NO | Latent log scoring rate: $\ln(\text{runs}/\text{ball})$. |
| `var_bat_rate` | `FLOAT64` | NO | Posterior variance of latent batting rate. |
| `theta_bat_surv` | `FLOAT64` | NO | Latent logit survival probability per delivery. |
| `var_bat_surv` | `FLOAT64` | NO | Posterior variance of batting survival. |
| `theta_bowl_haz` | `FLOAT64` | NO | Latent log wicket hazard: $\ln(\text{wickets}/\text{ball})$. |
| `var_bowl_haz` | `FLOAT64` | NO | Posterior variance of bowling hazard. |
| `theta_bowl_econ` | `FLOAT64` | NO | Latent log runs conceded: $\ln(\text{runs}/\text{ball})$. |
| `var_bowl_econ` | `FLOAT64` | NO | Posterior variance of bowling economy. |
| `theta_field` | `FLOAT64` | NO | Latent log fielding dismissal hazard. |
| `var_field` | `FLOAT64` | NO | Posterior variance of fielding hazard. |
| `r_bat` | `FLOAT64` | NO | Scaled native batting rating (centered at 1000). |
| `rd_bat` | `FLOAT64` | NO | Batting Rating Deviation / uncertainty ($\in [35, 350]$). |
| `r_bowl` | `FLOAT64` | NO | Scaled native bowling rating (centered at 1000). |
| `rd_bowl` | `FLOAT64` | NO | Bowling Rating Deviation / uncertainty ($\in [35, 350]$). |
| `r_field` | `FLOAT64` | NO | Scaled native fielding rating (centered at 500). |
| `rd_field` | `FLOAT64` | NO | Fielding Rating Deviation / uncertainty ($\in [150, 350]$). |
| `r_allround` | `FLOAT64` | NO | Strictly monotonic additive all-round rating. |
| `rd_allround` | `FLOAT64` | NO | Composite all-round rating deviation. |
| `vorp_rating` | `FLOAT64` | NO | Value Over Replacement in physical net runs added. |
| `recent_form_bat` | `FLOAT64` | NO | EWMA performance residual over recent matches. |
| `recent_form_bowl` | `FLOAT64` | NO | EWMA bowling residual over recent matches. |
| `inferred_role` | `STRING` | NO | Dynamic role code (`R1_OPENER` ... `R9_SPIN_SPECIALIST`). |
| `role_confidence` | `FLOAT64` | NO | Confidence probability mass of inferred role. |
| `role_uncertainty_flag` | `STRING` | YES | `DEBUTANT_INSUFFICIENT_HISTORY` if $N < 5$. |
| `identity_confidence_status`| `STRING`| NO | `VERIFIED` or `PROBABLE` (Babar Ali `c65e0275`). |
| `rating_status` | `STRING` | NO | `ACTIVE`, `INACTIVE` ($>365$ days), or `DEBUTANT`. |

---

### 2.2. `player_rating_history`
Chronological checkpoints capturing state evolution across match participations:
- **Partitioning**: Hive partition `match_format=.../year=...`.
- **File Name**: `history.parquet`.
- **Columns**: Identical schema to `player_rating_current`, preserving time-series trajectory.

---

### 2.3. `pre_match_snapshots`
Out-of-sample pre-match states evaluated immediately prior to match commencement for zero-lookahead backtesting and validation:
- **Partitioning**: Hive partition `match_format=.../year=...`.
- **File Name**: `pre_match.parquet`.

| Field Name | Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `player_id` | `STRING` | NO | Canonical player ID. |
| `match_id` | `STRING` | NO | Evaluated match identifier. |
| `match_date` | `STRING` | NO | Calendar date of match. |
| `pre_r_bat` | `FLOAT64` | NO | Pre-match batting rating prior to match observation. |
| `pre_rd_bat` | `FLOAT64` | NO | Pre-match batting uncertainty. |
| `pre_r_bowl` | `FLOAT64` | NO | Pre-match bowling rating. |
| `pre_rd_bowl` | `FLOAT64` | NO | Pre-match bowling uncertainty. |
| `pre_r_field` | `FLOAT64` | NO | Pre-match fielding rating. |
| `pre_rd_field` | `FLOAT64` | NO | Pre-match fielding uncertainty. |
| `pre_vorp` | `FLOAT64` | NO | Pre-match VORP in net runs added above replacement. |
| `inferred_role` | `STRING` | NO | Pre-match inferred dynamic role. |

---

### 2.4. `rating_metadata/_manifest.json`
Complete cryptographic manifest containing:
- Rating engine version (`4.0.0-phase4b`).
- Materialization UTC timestamp.
- Total files and total byte counts.
- Source input provenance and hashes.
- Run statistics (matches, participations, active states).
- Individual file SHA-256 checksums and file sizes.

---

> **Schema Sign-Off**: The rating store schema completely fulfills all Phase 4B data contracts. Partitioning prevents small-file bloat, all columns are explicitly typed, and physical units are strictly documented.
