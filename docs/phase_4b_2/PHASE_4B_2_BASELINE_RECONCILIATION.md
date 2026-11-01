# CricEngine AI — Phase 4B.2: Identical-Population Baseline Reconciliation Report

**Document ID**: `CRICENGINE-AUDIT-P4B2-001`  
**Milestone**: Phase 4B.2 — Statistical Findings Reconciliation  
**Author**: Lead Quantitative Researcher, Bayesian Statistician, and Independent Model Auditor  
**Status**: APPROVED & COMPLETE  
**Audit Scope**: Out-of-sample holdout period (2020-01-01 to 2024-12-31)  
**Sample Analyzed**: 4,951 unique active batting innings, 3,599 unique active bowling spells across 305 sampled matches (6,634 player-matches)  
**Analytical Artifacts**: [`data/analysis/phase_4b_2/baseline_comparison_results.json`](file:///Users/divygupta/desktop/DL_DATABASE/data/analysis/phase_4b_2/baseline_comparison_results.json), [`batting_tier_reconciliation.csv`](file:///Users/divygupta/desktop/DL_DATABASE/data/analysis/phase_4b_2/batting_tier_reconciliation.csv), [`bowling_tier_reconciliation.csv`](file:///Users/divygupta/desktop/DL_DATABASE/data/analysis/phase_4b_2/bowling_tier_reconciliation.csv)  

---

## 1. Executive Summary & Audit Mandate

In Phase 4B.1, it was reported that while simple rolling averages (BM-1) achieved lower overall point-prediction error on raw match counts than uncalibrated CA-HBSS ratings, CA-HBSS possessed a distinct predictive advantage for inexperienced players and debutants ($N < 5$ matches).

The Phase 4B.2 audit was mandated to independently re-evaluate this claim by comparing:
* **BM-0**: Population Average Baseline (format-specific static rate).
* **BM-1**: Historical Rolling 10-Match Average (using strictly prior matches).
* **BM-2**: Recency-Weighted EWMA (365-day half-life decay).
* **CA-HBSS**: Materialized pre-match rating engine with exponential rate link.

### Definitive Audit Finding: Formal Claim Withdrawal

When evaluated on **strictly identical, de-duplicated observations** across all experience tiers:
1. **CA-HBSS does NOT outperform BM-0 on cold-start debutants ($N = 0$)**: For players with zero prior format matches ($N = 144$), CA-HBSS has $z = 0$ ($\theta = 0, r = 1000$), which mathematically reduces to the exact population baseline BM-0 ($\text{MAE} = 5.926, \text{RMSE} = 8.996$).
2. **BM-1 (Rolling Average) outperforms CA-HBSS across ALL experience tiers**: Even for inexperienced debutants ($N < 5$ prior format appearances), BM-1 achieves lower MAE ($6.020$ vs $6.474$) and lower RMSE ($9.360$ vs $10.952$) than CA-HBSS.
3. **Formal Resolution**: The previous claim that CA-HBSS provides superior point forecasts for debutants was an artifact of uncalibrated baseline comparisons and the 9-way Cartesian merge explosion. **That claim is hereby formally WITHDRAWN.**

---

## 2. Methodology of Identical-Population Evaluation

To guarantee complete statistical validity:
1. **Zero Data Leakage**: All rolling features (BM-1, BM-2) and pre-match snapshots (CA-HBSS) were frozen as of calendar day $D-1$ strictly prior to match date $D$.
2. **De-Duplication**: In Phase 4B.1, unconstrained joining of `rolling_match` (3 window sizes: 5, 10, 20) and `rolling_time` (3 window sizes: 30, 90, 365) multiplied observation counts by $3 \times 3 = 9$. In Phase 4B.2, `rolling_match` was strictly filtered on `window_size == 10` and `rolling_time` on `window_days == 365`, restoring the true census of **4,951 unique batting innings** and **3,599 unique bowling spells**.
3. **Experience Classification**: Player experience was determined strictly using prior format appearances accumulated before the match date:
   * **Debutant**: Fewer than 5 prior appearances ($N < 5$).
   * **Moderate**: 5 to 9 prior appearances ($5 \le N < 10$).
   * **Established**: 10 or more prior appearances ($N \ge 10$).
4. **Cold-Start Handling**: Players with no prior history received the population baseline BM-0. No synthetic or forward-looking rolling averages were fabricated.

---

## 3. Overall Performance on Identical Unique Observations

### 3.1. Batting Runs Scored ($N = 4,951$ Unique Innings)

| Model Architecture | Evaluated ($N$) | MAE (Runs) | RMSE (Runs) | Prediction Bias | Mean Pred | Mean Actual | CRPS |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM-0: Population Average** | 4,951 | 6.713 | 10.058 | +1.635 | 22.086 | 20.452 | 5.195 |
| **BM-1: Rolling Average (M10)** | 4,951 | **6.346** | **9.894** | **+0.357** | **20.809** | **20.452** | **5.007** |
| **BM-2: Recency EWMA (365d)** | 4,951 | 6.396 | 10.017 | +0.481 | 20.932 | 20.452 | 5.048 |
| **CA-HBSS Rating Engine (Raw Link)**| 4,951 | 8.237 | 16.823 | +2.662 | 23.114 | 20.452 | 5.947 |

* **Observation**: BM-1 (10-match rolling average) achieves the lowest MAE ($6.346$), lowest RMSE ($9.894$), lowest bias ($+0.357$), and best continuous ranked probability score ($5.007$). Uncalibrated CA-HBSS over-predicts runs by $+2.662$ on average, causing higher RMSE due to tail sensitivity.

### 3.2. Bowling Wickets Taken ($N = 3,599$ Unique Spells)

| Model Architecture | Evaluated ($N$) | MAE (Wickets) | RMSE (Wickets) | Prediction Bias | Mean Pred | Mean Actual | CRPS |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM-0: Population Average** | 3,599 | **0.845** | **1.178** | **-0.145** | **0.958** | **1.103** | **0.624** |
| **BM-1: Rolling Baseline** | 3,599 | **0.845** | **1.178** | **-0.145** | **0.958** | **1.103** | **0.624** |
| **CA-HBSS Rating Engine (Raw Link)**| 3,599 | 1.441 | 2.605 | +1.008 | 2.111 | 1.103 | 0.968 |

* **Observation**: Bowling wickets are heavily constrained by Poisson discrete noise. Because average wickets per spell is $\approx 1.103$, uncalibrated exponential links project inflated expectations ($\bar{\hat{W}} = 2.111$), doubling the actual wicket rate.

### 3.3. Bowling Runs Conceded ($N = 3,599$ Unique Spells)

| Model Architecture | Evaluated ($N$) | MAE (Runs) | RMSE (Runs) | Prediction Bias | Mean Pred | Mean Actual | CRPS |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM-0: Population Average** | 3,599 | 8.395 | 11.466 | +1.013 | 30.184 | 29.170 | 6.141 |
| **BM-1: Rolling Average (M10)** | 3,599 | **8.238** | **11.285** | **-0.623** | **28.547** | **29.170** | **6.039** |
| **BM-2: Recency EWMA (365d)** | 3,599 | 8.286 | 11.381 | -0.672 | 28.499 | 29.170 | 6.088 |
| **CA-HBSS Rating Engine (Raw Link)**| 3,599 | 12.682 | 18.037 | -10.345 | 18.826 | 29.170 | 9.465 |

---

## 4. Stratified Analysis by Experience Tier

Evaluating models across experience tiers on strictly identical observations provides definitive evidence regarding cold-start behavior:

### 4.1. Batting Innings by Experience Tier

| Tier | Model | Sample ($N$) | MAE (Runs) | RMSE (Runs) | Bias | Mean Pred | Mean Act | CRPS |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Debutant ($N < 5$)** | BM-0: Population Average | 840 | 6.485 | 9.730 | +3.043 | 18.248 | 15.205 | 5.027 |
| | **BM-1: Rolling (Fallback)** | 840 | **6.020** | **9.360** | **+1.932** | **17.137** | **15.205** | **4.759** |
| | BM-2: Recency EWMA | 840 | 6.210 | 9.648 | +1.797 | 17.001 | 15.205 | 4.924 |
| | CA-HBSS Rating Engine | 840 | 6.474 | 10.952 | +2.903 | 18.108 | 15.205 | 4.819 |
| **Moderate ($5 \le N < 10$)**| BM-0: Population Average | 668 | 6.964 | 10.639 | +2.683 | 20.635 | 17.952 | 5.441 |
| | **BM-1: Rolling (Fallback)** | 668 | **6.111** | **9.444** | **-0.326** | **17.626** | **17.952** | **4.828** |
| | BM-2: Recency EWMA | 668 | 6.236 | 9.572 | +0.001 | 17.953 | 17.952 | 4.909 |
| | CA-HBSS Rating Engine | 668 | 7.349 | 13.541 | +2.526 | 20.478 | 17.952 | 5.336 |
| **Established ($N \ge 10$)**| BM-0: Population Average | 3,443 | 6.719 | 10.021 | +1.088 | 23.305 | 22.217 | 5.188 |
| | **BM-1: Rolling (Fallback)** | 3,443 | **6.471** | **10.103** | **+0.105** | **22.322** | **22.217** | **5.100** |
| | BM-2: Recency EWMA | 3,443 | 6.473 | 10.188 | +0.252 | 22.469 | 22.217 | 5.104 |
| | CA-HBSS Rating Engine | 3,443 | 8.840 | 18.497 | +2.630 | 24.847 | 22.217 | 6.341 |

### 4.2. Cold-Start Debutants with Exactly Zero Prior Appearances ($N = 144$)
When isolating genuine cold-start debutants ($N=0$ prior matches in format):

| Model | Observations | MAE (Runs) | RMSE (Runs) | Bias | Mean Pred | Mean Actual | CRPS |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM-0 (Population Mean)** | 144 | 5.926 | 8.996 | +3.921 | 16.442 | 12.521 | 4.599 |
| **BM-1 (Fallback to BM-0)**| 144 | 5.926 | 8.996 | +3.921 | 16.442 | 12.521 | 4.599 |
| **CA-HBSS Rating Engine** | 144 | 5.926 | 8.996 | +3.921 | 16.442 | 12.521 | 4.599 |

* **Mathematical Reason for Identity**: At debut ($N=0$), CA-HBSS initializes latent ability to prior $\theta = 0.0$ ($r = 1000.0, z = 0.0$). The exponential rate multiplier is $\exp(0) = 1.0$. The formula evaluates to $\text{balls\_faced} \times \text{FormatBaseSR}$, which is mathematically identical to BM-0.

---

## 5. Pure Available Subsets Evaluation (No Fallbacks)

To test whether fallbacks biased the comparison, we evaluated only the subset of innings where all historical baselines had genuine historical data ($N = 3,517$):

| Model Architecture | Valid ($N$) | MAE (Runs) | RMSE (Runs) | Prediction Bias | CRPS |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **BM-0: Population Average** | 3,517 | 7.315 | 10.727 | +1.377 | 5.603 |
| **BM-1 Pure: Rolling 10-Match** | 3,517 | **6.867** | **10.535** | **-0.080** | **5.381** |
| **BM-2 Pure: Recency EWMA** | 3,517 | 6.909 | 10.634 | +0.213 | 5.403 |
| **CA-HBSS Rating Engine** | 3,517 | 9.599 | 19.272 | +3.490 | 8.559 |

Even on the pure subset of established players with complete rolling history, BM-1 outperforms CA-HBSS on raw point forecasts.

---

## 6. Audit Conclusion & Final Verdict

1. **Definitive Finding**: On point forecasting of individual match counts (runs scored, wickets taken, runs conceded), simple 10-match rolling averages (BM-1) systematically outperform uncalibrated CA-HBSS across all experience tiers.
2. **Cold-Start Claim**: The claim that CA-HBSS beats historical baselines for debutants is mathematically refuted. For zero-appearance debutants, CA-HBSS is identical to the population baseline BM-0; for debutants with 1–4 matches, BM-1 outperforms CA-HBSS.
3. **Core Architectural Insight**: CA-HBSS is not designed as a direct count point-forecaster; it is a latent state representation of relative skill ($\theta$). Translating ratings into expected match runs requires the calibrated observation models of Phase 4C.
