# CricEngine AI — Step 4A: Feature Mathematical Definitions & Computational Contracts

> **Document Version**: `1.0`  
> **Date**: 2026-10-30  
> **Author**: Lead Data Engineer & Machine Learning Systems Architect  
> **Status**: **APPROVED COMPUTATIONAL CONTRACT**  
> **Boundary**: Design only. Specifies the exact mathematical contracts, sample thresholds, and missing-value semantics.

---

## 1. Missing-Value Philosophy & Zero-Conflation Policy

A central failure mode in naive cricket analytics is treating unobserved participation as zero performance:
- A player who does **not bowl** in a match did not bowl with an economy rate of `0.0`. Their economy is **`NULL` (unobserved)**.
- A batter who did **not bat** in a match did not score `0 (0)`. Their strike rate and average are **`NULL` (unobserved)**.
- A batter who was **not out** has 0 dismissals. Their batting average is undefined ($\frac{\text{Runs}}{0}$), not `0.0` or $\infty$.
- An evaluation window with **insufficient sample size** (e.g. 2 balls faced) must produce `NULL` rather than a wildly distorted metric (e.g. strike rate `300.0` or `0.0`).

### The Missing-Value Hierarchy
Every feature column in the feature store adheres to three distinct operational states:

$$\text{Value}(F) = \begin{cases}
v \in \mathbb{R} & \text{if } \text{Sample Count} \ge \text{Min Threshold } (N_{\text{min}}) \\
\text{NULL} & \text{if } 0 < \text{Sample Count} < N_{\text{min}} \quad \text{(Insufficient Sample Size)} \\
\text{NULL} & \text{if } \text{Sample Count} = 0 \quad \text{(Unobserved / Did Not Participate)}
\end{cases}$$

> [!CAUTION]
> **Zero-Conflation Rule**: In downstream machine learning datasets, `NULL` values must be handled via explicit missingness indicators (`is_null_feature = 1`) or Bayesian cohort shrinkage. Imputing `0.0` for missing strike rates, averages, or economy rates is strictly prohibited.

---

## 2. Batting Feature Specifications

### 2.1 Batting Strike Rate (`B_STRIKE_RATE`)
- **Mathematical Formula**:
  $$\text{B\_STRIKE\_RATE} = \frac{\sum \text{runs\_batter}}{\sum \text{balls\_faced}} \times 100$$
- **Numerator**: `SUM(runs_batter)` off deliveries where the player was the on-strike batter.
- **Denominator**: `COUNT(*)` of deliveries faced where `wides = 0` (no-balls count as balls faced; wides do not).
- **Minimum Sample Requirement**:
  - **T20**: Minimum **30 balls faced** across rolling window.
  - **ODI**: Minimum **60 balls faced** across rolling window.
  - **Test**: Minimum **100 balls faced** across rolling window.
- **Missing-Value Policy**: Returns `NULL` if balls faced $< N_{\text{min}}$. Never defaults to zero.
- **Format-Specific**: **Yes**. Strike rates must never be aggregated across formats without format-standardized $z$-scoring.
- **Competition-Specific**: **Yes**. Tracked within competition tier (e.g., IPL vs SMAT vs International T20I).
- **Feasibility Status**: **Directly Derivable from Canonical Data**.
- **SQL Specification**:
  ```sql
  CASE 
      WHEN COUNT(CASE WHEN wides = 0 THEN 1 END) >= 30 
      THEN (SUM(runs_batter) * 100.0) / COUNT(CASE WHEN wides = 0 THEN 1 END)
      ELSE NULL 
  END AS b_strike_rate
  ```

---

### 2.2 Batting Average (`B_AVERAGE`)
- **Mathematical Formula**:
  $$\text{B\_AVERAGE} = \frac{\sum \text{runs\_batter}}{\sum \text{dismissals}}$$
- **Numerator**: `SUM(runs_batter)`.
- **Denominator**: `COUNT(*)` where `player_out_id = batter_id` (excluding `retired hurt` and `retired not out`).
- **Minimum Sample Requirement**:
  - **T20**: Minimum **5 completed dismissals** ($D \ge 5$).
  - **ODI**: Minimum **8 completed dismissals** ($D \ge 8$).
  - **Test**: Minimum **10 completed dismissals** ($D \ge 10$).
- **Missing-Value Policy**: Returns `NULL` if dismissals $< D_{\text{min}}$. If a batsman has scored runs without being dismissed (e.g., 120 runs, 0 dismissals), returns `NULL` (or documented empirical Bayes shrinkage) rather than division-by-zero crash.
- **Format-Specific**: **Yes**.
- **Competition-Specific**: **Yes**.
- **Feasibility Status**: **Directly Derivable from Canonical Data**.
- **SQL Specification**:
  ```sql
  CASE 
      WHEN COUNT(dismissal_id) >= 5 
      THEN SUM(runs_batter) * 1.0 / COUNT(dismissal_id)
      ELSE NULL 
  END AS b_average
  ```

---

### 2.3 Boundary Percentage (`B_BOUNDARY_PCT`)
- **Mathematical Formula**:
  $$\text{B\_BOUNDARY\_PCT} = \frac{\sum \mathbb{I}(\text{runs\_batter} \in \{4, 6\})}{\sum \text{balls\_faced}} \times 100$$
- **Numerator**: Count of deliveries where batter scored 4 or 6.
- **Denominator**: Count of legal balls faced (`wides = 0`).
- **Minimum Sample Requirement**: Minimum **30 balls faced** in T20, **60** in ODI.
- **Missing-Value Policy**: `NULL` if balls faced $< N_{\text{min}}$.
- **Format-Specific**: **Yes**.
- **Feasibility Status**: **Directly Derivable from Canonical Data**.

---

### 2.4 Dot Ball Percentage Faced (`B_DOT_PCT`)
- **Mathematical Formula**:
  $$\text{B\_DOT\_PCT} = \frac{\sum \mathbb{I}(\text{runs\_total} = 0)}{\sum \text{balls\_faced}} \times 100$$
- **Numerator**: Deliveries where 0 total runs were scored (evaluates inability to rotate strike).
- **Denominator**: Count of balls faced (`wides = 0`).
- **Minimum Sample Requirement**: Minimum **30 balls faced**.
- **Missing-Value Policy**: `NULL` if below sample cutoff.
- **Format-Specific**: **Yes**.

---

### 2.5 Phase-Specific Batting Strike Rates (`B_SR_POWERPLAY`, `B_SR_DEATH`)
- **Mathematical Formula**:
  $$\text{B\_SR}_{\text{phase}} = \frac{\sum_{\text{phase}} \text{runs\_batter}}{\sum_{\text{phase}} \text{balls\_faced}} \times 100$$
- **Numerator / Denominator**: Restricts deliveries to `fact_ball_by_ball.match_phase = 'POWERPLAY'` or `'DEATH'`.
- **Minimum Sample Requirement**:
  - Powerplay: Minimum **20 balls faced in Powerplay**.
  - Death: Minimum **15 balls faced in Death overs**.
- **Missing-Value Policy**: `NULL` if player rarely bats in that phase.

---

## 3. Bowling Feature Specifications

### 3.1 Bowling Economy Rate (`W_ECONOMY_RATE`)
- **Mathematical Formula**:
  $$\text{W\_ECONOMY\_RATE} = \frac{\sum (\text{runs\_batter} + \text{wides} + \text{noballs})}{\sum \text{legal\_deliveries} / 6.0}$$
- **Numerator**: Total runs charged to the bowler (batter runs + wides + no-balls). Byes and leg-byes are excluded.
- **Denominator**: `COUNT(*)` where `is_legal_delivery = TRUE` divided by 6.0.
- **Minimum Sample Requirement**:
  - **T20**: Minimum **60 legal deliveries** (10 overs).
  - **ODI**: Minimum **120 legal deliveries** (20 overs).
  - **Test**: Minimum **180 legal deliveries** (30 overs).
- **Missing-Value Policy**: `NULL` if legal deliveries $< N_{\text{min}}$. Bowlers who did not bowl in a match receive `NULL`.
- **Format-Specific**: **Yes**.
- **Competition-Specific**: **Yes**.
- **Feasibility Status**: **Directly Derivable from Canonical Data**.
- **SQL Specification**:
  ```sql
  CASE 
      WHEN COUNT(CASE WHEN is_legal_delivery THEN 1 END) >= 60 
      THEN (SUM(runs_batter + wides + noballs) * 6.0) / COUNT(CASE WHEN is_legal_delivery THEN 1 END)
      ELSE NULL 
  END AS w_economy_rate
  ```

---

### 3.2 Bowling Strike Rate (`W_STRIKE_RATE`)
- **Mathematical Formula**:
  $$\text{W\_STRIKE\_RATE} = \frac{\sum \text{legal\_deliveries}}{\sum \text{wickets}}$$
- **Numerator**: Count of legal deliveries bowled.
- **Denominator**: Count of dismissals where `bowler_credited = TRUE` (bowled, caught, lbw, stumped, hit wicket).
- **Minimum Sample Requirement**: Minimum **5 wickets taken** ($W \ge 5$) and **60 legal balls bowled**.
- **Missing-Value Policy**: `NULL` if wickets $< 5$.
- **Format-Specific**: **Yes**.

---

### 3.3 Bowling Average (`W_AVERAGE`)
- **Mathematical Formula**:
  $$\text{W\_AVERAGE} = \frac{\sum (\text{runs\_batter} + \text{wides} + \text{noballs})}{\sum \text{wickets}}$$
- **Numerator**: Total bowler-conceded runs.
- **Denominator**: Credited wickets.
- **Minimum Sample Requirement**: Minimum **5 wickets** and **60 legal balls**.
- **Missing-Value Policy**: `NULL` if below sample threshold.

---

### 3.4 Maiden Overs Derived Rate (`W_MAIDEN_RATE`)
- **Mathematical Formula**:
  $$\text{W\_MAIDEN\_RATE} = \frac{\sum \mathbb{I}(\text{Over is Maiden})}{\sum \text{Completed Overs Bowled}}$$
- **Maiden Over Criterion (Empirical Scoring Law)**:
  An over qualifies as a maiden if and only if:
  $$\text{Legal Balls Bowled in Over} = 6 \quad \land \quad \sum (\text{runs\_batter} + \text{wides} + \text{noballs}) = 0$$
  *(Byes and leg-byes conceded do NOT spoil a maiden).*
- **Minimum Sample Requirement**: Minimum **10 completed overs**.
- **Missing-Value Policy**: `NULL` if $< 10$ overs.

---

### 3.5 Phase-Specific Bowling Economy (`W_ECON_POWERPLAY`, `W_ECON_DEATH`)
- **Numerator / Denominator**: Restricts balls bowled to `match_phase = 'POWERPLAY'` (overs 0-5 in T20) or `'DEATH'` (overs 15-19 in T20).
- **Minimum Sample Requirement**: Minimum **24 balls bowled** in that specific phase.
- **Missing-Value Policy**: `NULL` if bowler is not deployed in that phase.

---

## 4. Fielding Feature Specifications

### 4.1 Fielding Dismissal Involvement Rate (`F_INVOLVEMENT_RATE`)
- **Mathematical Formula**:
  $$\text{F\_INVOLVEMENT\_RATE} = \frac{\text{Catches} + \text{Stumpings} + \text{Run Outs}}{\text{Matches Fielded}}$$
- **Numerator**: Count of dismissals in `fact_dismissal_fielder` where `fielder_id = player_id`.
- **Denominator**: Matches where player fielded (`fielded_flag = TRUE` or `in_starting_xi = TRUE`).
- **Minimum Sample Requirement**: Minimum **10 matches fielded**.
- **Missing-Value Policy**: `NULL` if matches fielded $< 10$.

---

## 5. Multi-Dimensional Role Profile Features

### 5.1 Batting Load Index ($L_{\text{bat}}$)
- **Mathematical Formula**:
  $$L_{\text{bat}}(p, m) = \frac{\text{Balls Faced by } p \text{ in match } m}{\sum_{i \in \text{Team}} \text{Balls Faced by } i \text{ in match } m}$$
- **Range**: $[0.0, 1.0]$.
- **Interpretation**: Measures how central the player is to their team's batting resource consumption.

### 5.2 Bowling Load Index ($L_{\text{bowl}}$)
- **Mathematical Formula**:
  $$L_{\text{bowl}}(p, m) = \frac{\text{Legal Deliveries Bowled by } p \text{ in match } m}{\sum_{i \in \text{Team}} \text{Legal Deliveries Bowled in match } m}$$
- **Range**: $[0.0, 1.0]$.
- **Interpretation**: Measures the bowling workload shoulder by the player.

### 5.3 All-Rounder Balance Index ($\text{ABI}$)
- **Mathematical Formula**:
  $$\text{ABI}(p, m) = \frac{2 \cdot L_{\text{bat}}(p, m) \cdot L_{\text{bowl}}(p, m)}{L_{\text{bat}}(p, m) + L_{\text{bowl}}(p, m) + \epsilon}$$
  *(where $\epsilon = 10^{-6}$ prevents division by zero).*
- **Range**: $[0.0, 1.0]$.
- **Interpretation**: Approaches $1.0$ only for players who simultaneously face significant batting balls and bowl significant overs. Pure batters or pure bowlers have $\text{ABI} \approx 0.0$.

---

## 6. Summary Specification Table

| Feature Identifier | Canonical Name | Target Axis | Minimum Sample ($N_{\text{min}}$) | Missing Value Action | Format Specific? |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `B_STRIKE_RATE` | Batting Strike Rate | Batting Efficiency | 30 balls (T20) | Emit `NULL` | Yes |
| `B_AVERAGE` | Batting Average | Batting Longevity | 5 dismissals | Emit `NULL` | Yes |
| `B_BOUNDARY_PCT` | Boundary Ball % | Batting Power | 30 balls | Emit `NULL` | Yes |
| `B_DOT_PCT` | Dot Ball % Faced | Strike Rotation | 30 balls | Emit `NULL` | Yes |
| `B_SR_POWERPLAY` | Powerplay Strike Rate | Phase Batting | 20 PP balls | Emit `NULL` | Yes |
| `B_SR_DEATH` | Death Strike Rate | Phase Batting | 15 Death balls | Emit `NULL` | Yes |
| `W_ECONOMY_RATE` | Bowling Economy Rate | Bowling Control | 60 legal balls | Emit `NULL` | Yes |
| `W_STRIKE_RATE` | Bowling Strike Rate | Bowling Penetration | 5 wickets, 60 balls | Emit `NULL` | Yes |
| `W_AVERAGE` | Bowling Average | Bowling Cost | 5 wickets, 60 balls | Emit `NULL` | Yes |
| `W_MAIDEN_RATE` | Maiden Over Rate | Bowling Control | 10 overs | Emit `NULL` | Yes |
| `W_ECON_POWERPLAY` | Powerplay Economy | Phase Bowling | 24 PP balls | Emit `NULL` | Yes |
| `W_ECON_DEATH` | Death Economy | Phase Bowling | 24 Death balls | Emit `NULL` | Yes |
| `F_INVOLVEMENT_RATE`| Fielding Involvements | Fielding Impact | 10 matches | Emit `NULL` | Yes |
| `R_BATTING_LOAD` | Batting Resource Share | Role Profile | 1 team match | Compute $[0, 1]$ | Yes |
| `R_BOWLING_LOAD` | Bowling Resource Share | Role Profile | 1 team match | Compute $[0, 1]$ | Yes |
| `R_ALLROUNDER_INDEX`| Dual-Discipline Index | Role Profile | 1 team match | Compute $[0, 1]$ | Yes |
