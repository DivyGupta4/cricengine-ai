# CricEngine AI — Phase 4B.2: Observation Population Audit Report

**Document ID**: `CRICENGINE-AUDIT-P4B2-002`  
**Milestone**: Phase 4B.2 — Statistical Findings Reconciliation  
**Author**: Lead Quantitative Researcher, Bayesian Statistician, and Independent Model Auditor  
**Status**: APPROVED & COMPLETE  
**Evaluated Data Sources**: `pre_match_snapshots`, `player_match`, `rolling_match`, `rolling_time`  
**Analytical Artifacts**: [`data/analysis/phase_4b_2/reconciliation_table.csv`](file:///Users/divygupta/desktop/DL_DATABASE/data/analysis/phase_4b_2/reconciliation_table.csv), [`reconciliation_table.json`](file:///Users/divygupta/desktop/DL_DATABASE/data/analysis/phase_4b_2/reconciliation_table.json)  

---

## 1. Executive Summary & Audit Mandate

Phase 4B.1 reported four prominent observation counts in its holdout evaluation:
* 6,634 Pre-Match Snapshots
* 59,706 Player-Match Innings
* 44,559 Batting Observations
* 32,391 Bowling Observations

The Phase 4B.2 audit was charged with tracing the exact data-engineering lineage of these figures, establishing whether they reconcile with the underlying databases, and identifying the mathematical origin of any discrepancies.

### Definitive Finding: Discovery of 9-Way Cartesian Product
The 59,706 figure reported in Phase 4B.1 was not an independent population of player-match records. It was the result of an **unconstrained 9-way Cartesian product** caused by joining multi-window feature store tables without partition filtering:
$$\text{Reported Player-Matches} = 6,634 \times 3 \times 3 = \mathbf{59,706}$$
$$\text{Reported Batting Innings} = 4,951 \times 3 \times 3 = \mathbf{44,559}$$
$$\text{Reported Bowling Spells} = 3,599 \times 3 \times 3 = \mathbf{32,391}$$

The true, unique ground-truth sample in the 2020–2024 holdout consists of **6,634 unique player-matches**, containing **4,951 active batting innings** and **3,599 active bowling spells** across **305 sampled matches**.

---

## 2. Answers to the Ten Structural Audit Questions

### 1. What constitutes a pre-match snapshot?
A pre-match snapshot (`pre_match_snapshots/`) represents the exact state of a player's rating ($\boldsymbol{\theta}$, $RD$, $VORP$) immediately prior to a sampled match day.
* In `src/ratings/chronological_engine.py` (lines 208–227), snapshots are materialized using a **10% batch sampling filter**:
  ```python
  if batch_idx % 10 == 0:  # Sample every 10th batch to keep snapshot size manageable
      pre_match_snapshots.append({...})
  ```
* This sampling keeps storage compact while providing a representative longitudinal sample (19,642 total snapshots across 900 matches all-time; 6,634 snapshots across 305 matches in the 2020–2024 holdout).

### 2. What constitutes a player-match observation?
A player-match observation (`player_match/`) represents one individual player participating in one match. In Feature Store v3b, there are **200,709 total player-match records** across all 9,085 matches (2001–2026), and **68,689 player-match records** across 3,102 matches in the 2020–2024 holdout.

### 3. What constitutes a batting observation?
A batting observation is a player-match participation where the player actually batted and faced at least one delivery:
$$\text{Batting Innings} = \{i \in \text{Participations} \mid \text{balls\_faced}_i > 0\}$$
In the 2020–2024 sampled snapshot cohort ($N = 6,634$), exactly **4,951 participations** have $\text{balls\_faced} > 0$. The remaining **1,683 participations** represent Did Not Bat (DNB) or zero deliveries faced.

### 4. What constitutes a bowling observation?
A bowling observation is a player-match participation where the player bowled at least one legal delivery:
$$\text{Bowling Spell} = \{i \in \text{Participations} \mid \text{legal\_balls\_bowled}_i > 0\}$$
In the 2020–2024 sampled snapshot cohort ($N = 6,634$), exactly **3,599 participations** have $\text{legal\_balls\_bowled} > 0$. The remaining **3,035 participations** represent Did Not Bowl.

### 5. Can a player produce multiple batting observations in one match?
**No, not in the `player_match` feature store.** In Feature Store v3b, `player_match` is strictly aggregated at the **match level**, not the innings level. Even in multi-innings Test matches, a player has exactly one record in `player_match` containing the sum of runs scored and balls faced across both innings.

### 6. Can a player produce multiple bowling observations in one match?
**No.** Similarly, bowling statistics in `player_match` aggregate total balls bowled, runs conceded, and wickets taken across all innings of the match into a single row per player.

### 7. Are observations duplicated across formats or innings?
No. In the canonical database and feature store, primary keys `(match_id, player_id)` are strictly unique. Duplication occurred purely downstream in the audit evaluation script during table joining.

### 8. How are incomplete innings, DNB records, and zero-exposure records handled?
* **In Rating Engine Updates (`chronological_engine.py`)**: DNB records produce zero exposure ($B=0$). As verified in Phase 4B.1, zero-exposure participations bypass likelihood updates without numerical degradation (`zero_exposure_skips: 141,287`).
* **In Out-of-Sample Predictive Evaluation**: DNB records are appropriately excluded when evaluating strike rates or economy rates, as rate parameters are undefined when $B=0$.

### 9. How are retired hurt and retired out records handled?
* `retired_hurt`: Counted as not out (`is_dismissed = 0`). The balls faced and runs scored are preserved.
* `retired_out`: Counted as dismissed (`is_dismissed = 1`). Reconciled without duplicate participation records per the approved Step 4E remediation.

### 10. How are Test matches with multiple innings represented?
In `player_match`, a Test match is represented by **one consolidated row per player**. If a batter scores 40 in the 1st innings and 60 in the 2nd innings, `runs_scored` is 100 and `balls_faced` is the sum of both innings. `is_dismissed` is tracked via `dismissals_count` ($0, 1,$ or $2$).

---

## 3. The 9-Way Cartesian Explosion: Mathematical Proof

In `evaluate_holdout_predictive.py`, the evaluation dataset was constructed as follows:
```python
df = pd.merge(holdout_snaps, pm_df, on=["match_id", "player_id"])
df = pd.merge(df, rm_df, on=["match_id", "player_id"], how="left")
df = pd.merge(df, rt_df, on=["match_id", "player_id"], how="left")
```

### Table Structure in Feature Store v3b
1. **`rolling_match`**: Partitioned by Hive directory `window_size`. Contains **3 distinct windows** for every player-match:
   * `window_size = 5` (200,709 rows)
   * `window_size = 10` (200,709 rows)
   * `window_size = 20` (200,709 rows)
   * Total rows: $602,127$.
2. **`rolling_time`**: Partitioned by Hive directory `window_days`. Contains **3 distinct windows** for every player-match:
   * `window_days = 30` (200,709 rows)
   * `window_days = 90` (200,709 rows)
   * `window_days = 365` (200,709 rows)
   * Total rows: $602,127$.

### The Resulting Merge
When merging `holdout_snaps` ($N = 6,634$) on `["match_id", "player_id"]`:
* Merging with `rolling_match` without `window_size` filter expanded 6,634 rows to $6,634 \times 3 = 19,902$ rows.
* Merging with `rolling_time` without `window_days` filter expanded 19,902 rows to $19,902 \times 3 = \mathbf{59,706}$ rows!

Every observation was replicated exactly **9 times**, scaling:
* 6,634 player matches $\times 9 = \mathbf{59,706}$
* 4,951 active batting innings $\times 9 = \mathbf{44,559}$
* 3,599 active bowling spells $\times 9 = \mathbf{32,391}$

---

## 4. Master Observation Population Reconciliation Table

All figures derived from exact census queries across the datalake:

| Population Identifier | Unique Matches | Unique Players | Unique (Match, Player) Pairs | Materialized Rows | Exact Physical Role & Composition |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Canonical Matches Census (2001–2026)** | 9,085 | 6,974 | 200,709 | 200,709 | Total historical matches across ODI, T20, and Test |
| **Pre-Match Snapshots Materialized (All-Time)**| 900 | 4,336 | 19,642 | 19,642 | Materialized via 10% batch sampling (`batch_idx % 10 == 0`) |
| **Feature Store Holdout Census (2020–2024)** | 3,102 | 4,247 | 68,689 | 68,689 | Complete population of holdout player-matches |
| **Pre-Match Snapshots in Holdout (2020–2024)**| 305 | 2,329 | 6,634 | 6,634 | Sampled pre-match ratings cohort for holdout |
| **True 1-to-1 Evaluated Holdout Sample** | 305 | 2,329 | 6,634 | **6,634** | Ground-truth holdout sample (1 row per participation) |
| **True Active Batting Innings ($\text{BF} > 0$)** | 305 | 1,911 | 4,951 | **4,951** | Ground-truth active batting observations |
| **True Batting DNB ($\text{BF} = 0$)** | 284 | 912 | 1,683 | **1,683** | Participated in match but faced 0 balls |
| **True Active Bowling Spells ($\text{LB} > 0$)** | 304 | 1,414 | 3,599 | **3,599** | Ground-truth active bowling observations |
| **True Bowling DNB ($\text{LB} = 0$)** | 305 | 1,178 | 3,035 | **3,035** | Participated in match but did not bowl |
| **Phase 4B.1 Cartesian Expanded Total** | 305 | 2,329 | 6,634 | **59,706** | 9-way Cartesian product: $6,634 \times 3 \times 3$ |
| **Phase 4B.1 Cartesian Expanded Batting**| 305 | 1,911 | 4,951 | **44,559** | 9-way Cartesian product: $4,951 \times 3 \times 3$ |
| **Phase 4B.1 Cartesian Expanded Bowling**| 304 | 1,414 | 3,599 | **32,391** | 9-way Cartesian product: $3,599 \times 3 \times 3$ |

---

## 5. Audit Conclusion & Findings

1. **Reconciliation Status**: 100% of all observation populations are fully and unambiguously reconciled.
2. **Data Integrity**: The underlying database (`cricengine.duckdb`) and feature store (`feature_store_v3b`) are completely free of duplicate rows or relational inconsistencies.
3. **Cartesian Artifact**: The 59,706, 44,559, and 32,391 figures reported in Phase 4B.1 were artifacts of an unconstrained multi-window join in the evaluation script, perfectly explained by the $3 \times 3 = 9$ window factor.
4. **Correct Holdout Census**: All subsequent predictive and calibration analyses must be conducted on the true de-duplicated sample of **4,951 batting innings** and **3,599 bowling spells**.
