# CricEngine AI — Phase 4B.1: VORP Validation Report

**Document ID**: `CRICENGINE-AUDIT-P4B1-003`  
**Milestone**: Phase 4B.1 — Rating Store Integrity & Predictive Validity Audit  
**Author**: Lead Quantitative Model Auditor, Bayesian Statistician, and Data Integrity Engineer  
**Status**: APPROVED & COMPLETE  
**Evaluated Target**: VORP calculations in `data/datalake/rating_store_v4/player_rating_current/`  
**Sample Analyzed**: 9,406 active player-format states  

---

## 1. Executive Summary & Audit Mandate

Value Over Replacement Player (VORP) translates multi-dimensional latent ability parameters ($\boldsymbol{\theta}$) and display ratings into an actionable single-number metric of net marginal value over an freely available fringe replacement player. This audit inspects the mathematical formulation of VORP implemented in Phase 4B (`src/ratings/vorp.py`), evaluates the empirical distribution of VORP across all formats, audits the treatment of sub-replacement negative values, and conducts sensitivity analysis on replacement baseline definitions.

### Dimensional Determination: PASS WITH LIMITATIONS

| Evaluation Dimension | Target Standard | Empirical Finding | Status |
| :--- | :--- | :--- | :--- |
| **Mathematical Formulation** | Weighted marginal surplus above baseline | Formulated correctly per Phase 4A.1 specs | **PASS** |
| **Negative Value Preservation** | Sub-replacement liabilities must not be zeroed | Fully preserved; min VORP is $-1.5$ in T20 | **PASS** |
| **Role Weight Differentiation** | Role-appropriate weighting of skill components | Strictly enforced across 4 inferred roles | **PASS** |
| **Synergy Isolation** | Individual states must not fabricate match synergy | `RosterSynergyBonus = 0.0` across all records | **PASS** |
| **Replacement Baseline Calibration** | Balanced marginal surplus across disciplines | Uniform 650.0 causes bowling dominance | **LIMITATION** |

---

## 2. VORP Mathematical Architecture

The VORP of player $i$ in format $m$ is formulated as:
$$\text{VORP}_i = \sum_{d \in \{\text{bat}, \text{bowl}, \text{field}\}} w_{\text{role}(i), d} \cdot \left(\frac{r_{i, d} - R_{\text{rep}, d}}{100.0}\right) + \text{SynergyBonus}$$

Where:
* $R_{\text{rep}, d} = 650.0$ points for all disciplines $d$ in the initial baseline.
* The divisor $100.0$ normalizes 100 rating points to 1.0 VORP unit (roughly equivalent to 1 win percentage point or 10–12 net runs of value).
* Role weights $\mathbf{w}_{\text{role}}$ are dynamically assigned based on point-in-time `inferred_role`:

| Inferred Role | $w_{\text{bat}}$ | $w_{\text{bowl}}$ | $w_{\text{field}}$ | Sum of Weights |
| :--- | :---: | :---: | :---: | :---: |
| **Pure Batter** (`BATTER`) | 0.85 | 0.05 | 0.10 | 1.00 |
| **Pure Bowler** (`BOWLER`) | 0.05 | 0.85 | 0.10 | 1.00 |
| **All-Rounder** (`ALL_ROUNDER`) | 0.45 | 0.45 | 0.10 | 1.00 |
| **Wicketkeeper** (`WICKETKEEPER`) | 0.80 | 0.00 | 0.20 | 1.00 |

* **Synergy Isolation**: In `src/ratings/vorp.py`, individual player rating states strictly set `SynergyBonus = 0.0`. Roster complementarity is a joint XI-level property to be evaluated in Phase 5 optimization, not an inherent attribute of an isolated player.

---

## 3. Empirical VORP Distribution Across Formats

### 3.1. Summary Statistics by Format

| Match Format | Sample Size ($N$) | Mean | Std | Median | P05 | P95 | Min | Max |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **T20** | 6,321 | 4.60 | 3.21 | 4.21 | 0.24 | 10.51 | -1.54 | 23.68 |
| **ODI** | 2,015 | 8.89 | 5.12 | 8.04 | 1.39 | 18.01 | -0.12 | 26.83 |
| **TEST** | 1,070 | 15.62 | 8.41 | 13.72 | 4.49 | 31.72 | -0.04 | 45.31 |

### 3.2. Distribution by Experience Level (T20 Format)
* **Debutant / Fringe ($N < 5$ matches)**: Mean VORP = $2.41$ (Std $1.82$, Median $2.10$)
* **Moderate ($5 \le N < 10$ matches)**: Mean VORP = $3.85$ (Std $2.45$, Median $3.50$)
* **Established ($N \ge 10$ matches)**: Mean VORP = $6.72$ (Std $2.91$, Median $6.14$)

The steady rise in mean VORP from debutants to established players reflects both selection bias (better players play more matches) and Bayesian evidence accumulation separating elite performers from replacement level.

---

## 4. Preservation of Negative VORP Values

A critical requirement of Phase 4A.1 was that sub-replacement performance must not be artificially censored or clamped to zero. Players who perform worse than the 650.0 replacement threshold represent net liabilities to team win probability.

* **Audit Verification**:
  * In T20, exactly 184 player states exhibit $\text{VORP} < 0.0$, reaching a minimum of $-1.54$.
  * In ODI, 9 player states exhibit $\text{VORP} < 0.0$, reaching a minimum of $-0.12$.
  * In Test, 2 player states exhibit $\text{VORP} < 0.0$, reaching a minimum of $-0.04$.
  * Zero clamping functions (`max(0, ...)` or `np.clip`) were detected in the production VORP pipeline. Negative values flow unhindered into the rating store.

---

## 5. Replacement Baseline Sensitivity Analysis

We conducted read-only sensitivity experiments perturbing the baseline replacement threshold $R_{\text{rep}}$ by $\pm 50$ and $\pm 100$ rating points from its current setting of $650.0$:

### Sensitivity in T20 Format ($N = 6,321$)

| Threshold $R_{\text{rep}}$ | Mean VORP | Std VORP | Median | Min VORP | Max VORP | % Below Zero |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **550.0** (Loose Replacement) | 5.60 | 3.21 | 5.21 | -0.54 | 24.68 | 0.8% |
| **600.0** | 5.10 | 3.21 | 4.71 | -1.04 | 24.18 | 1.8% |
| **650.0 (Current Baseline)** | **4.60** | **3.21** | **4.21** | **-1.54** | **23.68** | **2.9%** |
| **700.0** | 4.10 | 3.21 | 3.71 | -2.04 | 23.18 | 5.4% |
| **750.0** (Strict Replacement) | 3.60 | 3.21 | 3.21 | -2.54 | 22.68 | 11.2% |

* **Spearman Rank Correlation**: $\rho = 1.0000$ across all tested uniform thresholds. A uniform linear shift in replacement level changes the absolute origin but perfectly preserves relative player ranking.

---

## 6. Critical Audit Limitation: Replacement Level Asymmetry

While uniform threshold shifts preserve intra-role rankings, the use of a **single uniform replacement threshold ($650.0$) across both batting and bowling** introduces a significant cross-discipline distortion:

1. **Empirical Baseline Discrepancy**:
   * Average batting display rating: $\bar{r}_{bat} \approx 899.3$ (T20), generating an average batting surplus of $899.3 - 650.0 = +249.3$ points ($+2.49$ VORP units).
   * Average bowling display rating: $\bar{r}_{bowl} \approx 1177.0$ (T20), generating an average bowling surplus of $1177.0 - 650.0 = +527.0$ points ($+5.27$ VORP units).
2. **Consequence**:
   * Bowling surplus is more than **2.1 times larger** than batting surplus for equivalent relative performance.
   * For genuine all-rounders ($w_{bat} = 0.45, w_{bowl} = 0.45$), over 68% of total VORP is determined by bowling performance rather than batting performance.
3. **Audit Recommendation for Phase 4C / Phase 5**:
   * Calibrate discipline-specific replacement baselines:
     $$R_{\text{rep}, bat} \approx 650.0, \quad R_{\text{rep}, bowl} \approx 900.0$$
   * This will equalize the expected surplus of average players across disciplines and ensure that Playing XI selection algorithms do not artificially overweight bowling over batting.

**Dimension 3 Determination: PASS WITH LIMITATIONS**
