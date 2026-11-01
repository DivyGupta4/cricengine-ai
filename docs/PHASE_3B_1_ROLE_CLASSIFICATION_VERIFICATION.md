# CricEngine AI — Phase 3B.1: Role Classification Verification Report

> **Authority**: Phase 3B.1 Final Integrity Verification (Part B)  
> **Status**: ACCEPTED WITH LIMITATIONS  
> **Date**: November 2026  
> **Target Dataset**: [dim_player_master_enriched.parquet](file:///Users/divygupta/desktop/DL_DATABASE/data/datalake/enrichment_v3b/dim_player_master_enriched.parquet)  
> **Curated Database Status**: READ-ONLY VERIFIED (SHA-256: `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae`)

---

## 1. Executive Summary & Verification Determination

Under Phase 3B.1 Part B, we conducted a comprehensive methodological inspection of the player role classifications reported in Phase 3B:
- **`All-Rounder`**: 3,149 players (44.9%)
- **`Specialist Batter`**: 2,771 players (39.5%)
- **`Specialist Bowler`**: 937 players (13.4%)
- **`Reserve / Non-Active`**: 157 players (2.2%)
- **Total Canonical Players**: **7,014**

### Key Verification Findings:
1. **Four-Tier Role Separation**: The ontology correctly disentangles four distinct concepts:
   - `officially_listed_role`: Third-party external registered role (e.g., "Wicketkeeper batter", "Top-order batter").
   - `observed_historical_role`: Career-wide empirical classification based on balls faced, balls bowled, and match involvement.
   - `derived_statistical_role`: Strictly preserved as **100% `NULL`** across all 7,014 players.
   - `current_role`: Sourced synthesis of official role and historical performance.
2. **Identification of Temporal Limitation**:
   - `observed_historical_role` and `current_role` (which populates `primary_role` in `player_match`) are computed across each player's **entire career** in the database.
   - Consequently, `primary_role` is a **static dimension attribute** (analogous to nationality or date of birth), rather than an expanding, point-in-time role.
   - **Crucial Safeguard**: None of the rolling performance features (`rolling_batting_avg`, `rolling_economy_rate`, `decayed_batting_sr`, etc.) rely on `primary_role`. Furthermore, dynamic all-rounder contribution is captured at the match grain by the point-in-time **`allrounder_balance_index` (ABI)**.
   - However, because `primary_role` incorporates full-career participation, downstream rating models must **not** treat `primary_role` as a strictly pre-match observed feature for historical matches early in a player's career.

**Final Gate Determination**: **`ACCEPTED WITH LIMITATIONS`**

---

## 2. Methodological Inspection & Audit Questions

### 2.1. Exact Classification Rules and Thresholds
The empirical logic for `observed_historical_role` in [`etl/enrich_player_master_v3b.py`](file:///Users/divygupta/desktop/DL_DATABASE/etl/enrich_player_master_v3b.py) applies the following deterministic decision tree:

```
Let:
  M   = Total recorded match appearances
  BM  = Matches in which player batted (batted_flag = TRUE)
  BoM = Matches in which player bowled (bowled_flag = TRUE)
  BF  = Total balls faced across career
  R   = Total runs scored across career
  BB  = Total legal balls bowled across career

Rules:
1. IF BM == 0 AND BoM == 0:
     Role = "Reserve / Non-Active" (157 players)
2. ELSE IF (BB >= 60 OR (M > 0 AND BoM / M >= 0.20)) 
       AND (BF >= 60 OR R >= 50 OR (M > 0 AND BM / M >= 0.25)):
     Role = "All-Rounder" (3,149 players)
3. ELSE IF (BB >= 60 OR BoM > BM):
     Role = "Specialist Bowler" (937 players)
4. ELSE:
     Role = "Specialist Batter" (2,771 players)
```

### 2.2. Treatment of Wicketkeepers
- In `officially_listed_role`: Wicketkeepers are explicitly identified (e.g., MS Dhoni, Quinton de Kock, Jos Buttler, and Rishabh Pant are classified as `"Wicketkeeper batter"`).
- In `observed_historical_role`: Because wicketkeeping activity (stumpings and wicketkeeper catches) does not involve delivering balls, keepers who face $\ge 60$ balls and do not bowl $\ge 60$ balls are categorized empirically as `Specialist Batter`.
- In `current_role`: Official listed profile takes precedence, preserving their designation as wicketkeepers where available.

### 2.3. Treatment of Players with Limited Samples
- Players with $<60$ balls bowled and $<60$ balls faced (e.g. associate cricketers with 1–2 matches):
  - If they bowled in more matches than they batted, they are assigned `Specialist Bowler`.
  - If they batted in at least one match, they are assigned `Specialist Batter`.
  - If they never batted or bowled, they are assigned `Reserve / Non-Active`.
- **Audit Assessment**: While statistically defensible as a baseline heuristic, assigning `All-Rounder` or `Specialist` to a player with only 1 appearance carries high parameter uncertainty. Downstream models should apply Bayesian shrinkage based on sample size.

### 2.4. Format-Specific Role Evaluation
- **Current State**: Roles are currently aggregated across all formats (T20, ODI, Test) rather than computed per format.
- **Audit Assessment**: Certain players function as genuine all-rounders in T20s but as specialist batters or bowlers in Tests (e.g. Marcus Stoinis, Glenn Maxwell). Downstream rating models should compute format-specific activity weights.

### 2.5. Role Evolution Over Time
- **Current State**: In `dim_player_master_enriched`, the role is static across a player's entire tenure.
- **Audit Assessment**: A player who begins as a specialist bowler and transitions into a top-order all-rounder (e.g., Steve Smith starting as a leg-spinner and evolving into a specialist batter, or Ravindra Jadeja's increasing batting burden) receives a static role. Dynamic point-in-time role evolution is captured by `allrounder_balance_index` in `player_match`, not by `primary_role`.

---

## 3. Difference Between the Four Role Dimensions

| Dimension | Description | Populated Count | Null Count | Provenance Category |
| :--- | :--- | :---: | :---: | :--- |
| **`officially_listed_role`** | Registered playing role from third-party profile (e.g. ESPNcricinfo). | 34 | 6,980 | `AUTHORITATIVELY SOURCED` / `UNAVAILABLE` |
| **`observed_historical_role`** | Empirical classification based on full career box scores. | 7,014 | 0 | `DIRECTLY OBSERVED` |
| **`derived_statistical_role`** | Output of unsupervised clustering / GMM / k-means. | **0** | **7,014** | **`UNAVAILABLE` (Strictly Unmodelled)** |
| **`current_role`** | Sourced synthesis of official role and historical performance. | 7,014 | 0 | `DERIVED` |

---

## 4. Temporal Consistency & Lookahead Leakage Audit

We rigorously evaluated whether `primary_role` or any rolling feature in `data/datalake/feature_store_v3b/` introduces lookahead leakage:

1. **Rolling Performance Features**:
   - `rolling_batting_avg`, `rolling_batting_sr`, `rolling_economy_rate`, `decayed_batting_sr`, etc. are strictly computed over preceding matches $t < T_{\text{match}}$ ordered by `(start_date, match_type_number)`.
   - **Zero Lookahead Leakage**: Verified. No future deliveries or future match results enter rolling feature calculations.
2. **Dimension Attributes in `player_match`**:
   - `primary_role` is a dimension descriptor joined from `dim_player_master_enriched`.
   - **Limitation**: For early matches in a player's career, `primary_role` reflects their lifetime career status rather than their status at match $T$. For example, a debutant who eventually becomes an all-rounder is labeled `All-Rounder` on debut.
   - **Remediation for Phase 4**: Machine learning and rating models must not use `primary_role` as an exogenous pre-match feature for debutants, or must use expanding pre-match ball counts instead.

---

## 5. Verification Determination & Acceptance Limitations

- **Determination**: **`ACCEPTED WITH LIMITATIONS`**
- **Documented Limitations**:
  1. `primary_role` in `player_match` is a career-aggregate descriptor and must not be interpreted as an expanding point-in-time pre-match feature.
  2. Format-specific role variations (e.g., T20 all-rounder vs Test batter) are not distinguished in `dim_player_master_enriched`.
  3. `derived_statistical_role` remains 100% `NULL`, as intended, awaiting formal unsupervised modelling in future milestones.
