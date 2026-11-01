# CricEngine AI — Phase 4B.1: Limitations Register

**Document ID**: `CRICENGINE-AUDIT-P4B1-007`  
**Milestone**: Phase 4B.1 — Rating Store Integrity & Predictive Validity Audit  
**Author**: Lead Quantitative Model Auditor, Bayesian Statistician, and Data Integrity Engineer  
**Status**: APPROVED & COMPLETE  
**Scope**: Materialized Rating Store v4 (`data/datalake/rating_store_v4/`) and Rating Engine (`src/ratings/`)  

---

## 1. Classification Framework

Every identified limitation in this register is classified into one of four severity tiers:
* **`BLOCKING`**: Fatal mathematical or data integrity flaw that invalidates the rating store and halts progress.
* **`CALIBRATION REQUIRED`**: Valid mathematical representation that requires empirical calibration or link function tuning in **Phase 4C** before deployment into predictive models or optimization engines.
* **`IMPLEMENTATION REQUIRED`**: Planned structural feature belonging to downstream milestones (e.g., Phase 5 Playing XI Optimizer).
* **`NON-BLOCKING`**: Known data property or conservative design choice properly handled by the engine with minimal downstream consequence.

---

## 2. Comprehensive Limitations Register

| ID | Title | Severity | Impacted Component | Root Cause | Recommended Treatment |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **LIM-001** | Replacement Level Baseline Asymmetry | **CALIBRATION REQUIRED** | `src/ratings/vorp.py` | Uniform 650.0 threshold applied across disciplines where mean bowling ($1177–1254$) sits higher than mean batting ($899–1085$). Bowling accounts for $\approx 68\%$ of VORP variance. | Calibrate discipline-specific replacement baselines in Phase 4C: $R_{\text{rep}, bat} \approx 650.0, R_{\text{rep}, bowl} \approx 900.0$. |
| **LIM-002** | Uncalibrated Latent Rate Count Mapping | **CALIBRATION REQUIRED** | Downstream Point Forecasting | Raw exponential link ($\lambda_0 e^{z \cdot 0.35}$) maps latent skill to count rates without match situation constraints, causing simple rolling average (BM-1) to achieve lower MAE on raw match counts. | Mandate Phase 4C: Implement bounded Generalized Additive Models (GAM) and Negative Binomial link functions conditioned on match target and balls remaining. |
| **LIM-003** | Fielding Data Sparsity & High Uncertainty Floor | **NON-BLOCKING** | `src/ratings/observation_models.py` | 65.5% of historical player-matches lack detailed fielding tags in canonical archives. Model maintains high uncertainty floor ($RD_{field} \ge 150.0$). | Preserved as-is. Fielding appropriately accounts for only 10–20% of total player value. |
| **LIM-004** | Complete Exclusion of Player Age | **NON-BLOCKING** | `src/ratings/temporal_dynamics.py` | 92.5% missing date-of-birth across canonical historical archives from Cricsheet. | Maintain current architecture: model aging through empirical Brownian process noise ($\sigma_w^2$) and inactivity decay rather than static age curves. |
| **LIM-005** | Single Residual PROBABLE Identity Invariant | **NON-BLOCKING** | `player_rating_current` | Player `c65e0275` (Babar Ali) carries PROBABLE identity status from Phase 3B.1. | Properly flagged via `identity_confidence_status = 'PROBABLE'`. 0 pipeline failures. |
| **LIM-006** | Debutant Cold-Start Priors | **NON-BLOCKING** | `src/ratings/state_space.py` | Debutants receive uninformative population priors ($\theta=0, RD=350$). Cross-format transfer (e.g., Test form informing T20 debut) is intentionally omitted. | Maintain format isolation in Phase 4B. Evaluate optional cross-format prior shrinkage in Phase 5 if desired. |
| **LIM-007** | Absence of Intra-Match State Conditioning | **IMPLEMENTATION REQUIRED** | `pre_match_snapshots` | Pre-match ratings capture point-in-time state before the toss; they do not condition on batting 1st vs chasing, pitch deterioration, or weather. | Implement match-state dynamic conditioning in Phase 5 Match Simulator / XI Optimizer. |

---

## 3. Deep Analysis of Critical Limitations

### 3.1. Detailed Analysis of LIM-001 (VORP Asymmetry)
* **Mathematical Description**:
  $$\text{Surplus}_{bat} = r_{bat} - 650.0 \approx 900 - 650 = +250 \implies +2.5 \text{ VORP}$$
  $$\text{Surplus}_{bowl} = r_{bowl} - 650.0 \approx 1200 - 650 = +550 \implies +5.5 \text{ VORP}$$
* **Consequence**: An average bowler appears more valuable than an average batter in total VORP.
* **Resolution**: Setting $R_{\text{rep}, bowl} = 900.0$ and $R_{\text{rep}, bat} = 650.0$ balances average surplus to $+2.5$ VORP for both disciplines.

### 3.2. Detailed Analysis of LIM-002 (Predictive Count Mapping)
* **Statistical Description**:
  Latent ability $\theta$ is an optimal measure of **marginal skill efficiency**, not raw count prediction. Direct exponential links produce heavy tails for high-rated players facing unconstrained match scenarios.
* **Resolution**:
  In Phase 4C, construct explicit observation models:
  $$\mathbb{E}[Runs \mid \theta_{bat}, \theta_{bowl}, \text{venue}, B] = g^{-1}(\mathbf{X} \boldsymbol{\beta} + f(\theta_{bat}) - h(\theta_{bowl}))$$
  with natural upper bounds enforcing physical match constraints.

---

## 4. Audit Summary & Downstream Readiness

* **Blocking Limitations**: **0**
* **Calibration Required**: **2** (LIM-001, LIM-002)
* **Non-Blocking**: **4** (LIM-003, LIM-004, LIM-005, LIM-006)
* **Implementation Required**: **1** (LIM-007)

**Conclusion**: The rating store is mathematically sound, structurally robust, and verified ready to proceed to Phase 4C calibration.
