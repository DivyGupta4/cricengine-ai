# CricEngine AI — Phase 4C Limitations Report
## Data, Statistical & Model Limitations Inventory

**Document ID**: `CRIC-DOC-P4C-009`  
**Milestone**: Phase 4C — Integrated Predictive Modelling & VORP  
**Status**: COMPLETE & VERIFIED  
**Author**: Quantitative Model Auditor & Statistical Research Specialist  

---

### 1. Purpose & Guiding Principles

In accordance with CricEngine AI governance, this report provides an **unvarnished, statistically honest inventory** of known limitations, residual edge cases, and structural boundaries of the Phase 4C predictive and valuation layer. Identifying what a model *cannot* do is as important as documenting what it can do.

---

### 2. Comprehensive Limitations Inventory

#### 2.1 Limitation 1: Batting Early Dismissal Point-Mass (The "Duck" Phenomenon)
* **Description**: In cricket batting, dismissal is an absorbing Markov state that can occur on any delivery. Over **25% of all batting innings terminate at 0 to 5 runs**, regardless of whether the batsman is an amateur or an elite international.
* **Statistical Impact**: The Phase 4C model parameterizes match runs using a compound Negative-Binomial distribution matching the marginal mean and total variance. For an expected mean of $30$ runs, the lower $5\%$ quantile is placed at $\approx 8$ runs. Consequently, every dismissal between 0 and 7 runs falls below the lower bound, causing empirical 90% coverage to register at **62.96%** (a -27.04% error, almost entirely concentrated in the lower tail).
* **Mitigation Recommendation**: In future simulation models (Phase 5), implement a two-component hurdle model or Zero-Inflated Negative Binomial (ZINB) distribution that models early dismissal hazard separately from post-settled scoring rate.

#### 2.2 Limitation 2: The Bowling $L_1$ Median Paradox
* **Description**: Over **52% of all bowling spells result in exactly 0 or 1 wicket**.
* **Statistical Impact**: Under Mean Absolute Error ($L_1$ norm), a trivial static forecast of $\approx 1.0$ wicket mathematically minimizes absolute error across the sample ($0.94$ MAE), outperforming dynamic models ($1.04$ MAE). However, static models provide zero correlation ($r=0$) and cannot rank bowlers.
* **Mitigation Recommendation**: Evaluate bowling predictions using strictly proper scoring rules (Brier score, Winkler score, discrete CRPS) and rank correlations ($\rho, \tau$) rather than MAE.

#### 2.3 Limitation 3: High Fielding Observational Noise
* **Description**: Fielding dismissals (catches, run-outs, stumpings) occur with low base rates ($0.35$ to $0.45$ involvements per match for non-keepers). Furthermore, whether a catch is hit toward a specific fielder depends heavily on bowling line, batsman shot selection, and pitch bounce.
* **Statistical Impact**: Epistemic uncertainty remains wide even after dozens of matches. Phase 4C enforces an intentional epistemic uncertainty floor:
  $$RD_{field} \ge 150.0$$
* **Mitigation Recommendation**: Do not allow fielding VORP to dominate player selection. Fielding VORP should act strictly as a marginal tie-breaker ($\le 15\%$ of total player value).

#### 2.4 Limitation 4: Truncation from Unobserved Live Match Dynamics
* **Description**: Pre-match predictions evaluate player opportunity based on starting order position and role. However, live match conditions frequently truncate player opportunity:
  * In small run chases (e.g. chasing 110 runs in an ODI), top-order batsmen hit 40* and the match ends before middle-order batsmen can bat.
  * In Test matches, captain declarations and weather interruptions truncate innings.
* **Statistical Impact**: Top-decile predicted runs ($55.1$) exceed observed actuals ($41.6$) by $\approx 13$ runs, yielding a decile reliability slope of $0.695$.
* **Mitigation Recommendation**: For Playing XI simulation, condition predictions dynamically on live game states (target remaining, balls remaining, wickets in hand) rather than purely static pre-match expectations.

#### 2.5 Limitation 5: Aggregation of Micro Match-Up Dynamics
* **Description**: Phase 4C conditions predictions on team-level opposition bowling quality ($OBQ$) and opposition batting quality ($OBatQ$). It does not model explicit micro-level match-ups (e.g., left-arm pacer inswing against right-hand top-order batsmen, or wrist-spin against lower-order pinch hitters).
* **Mitigation Recommendation**: In downstream tactics modules, incorporate pairwise synergy and head-to-head match-up matrices without violating overall model calibration.
