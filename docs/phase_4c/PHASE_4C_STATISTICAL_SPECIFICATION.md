# CricEngine AI — Phase 4C Statistical Specification
## Integrated Predictive Modelling, Statistical Calibration & VORP Implementation

**Document ID**: `CRIC-DOC-P4C-001`  
**Milestone**: Phase 4C — Integrated Predictive Modelling & VORP  
**Status**: APPROVED & IMPLEMENTED  
**Author**: Lead Statistical Modeller & Bayesian Systems Architect  
**Implementation Modules**: [`src/predictive/`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/)  

---

### 1. Executive Summary & Purpose

Phase 4C bridges the gap between the point-in-time latent ratings materialized by the Phase 4B CA-HBSS (Context-Adjusted Historical Bayesian State-Space) rating engine and calibrated, probabilistic match performance forecasts and player valuations.

As proven in the Phase 4B.2 reconciliation, latent ratings $r \in [100, 1900]$ and their standardized counterparts $z = (r - 1000) / 350$ represent *relative marginal efficiencies*, not unconstrained raw match counts. Uncalibrated exponential links ($\lambda_0 e^{0.35 z}$) over-predict counts for elite players because match constraints (overs remaining, targets, declarations, wickets fallen) bound player opportunity.

Phase 4C specifies and implements an integrated, statistically defensible architecture:
1. **Two-Stage Observation Models**: Separate Stage 1 (Exposure/Opportunity) from Stage 2 (Efficiency/Rate).
2. **Tempered Generalized Linear Links**: Log-link functions calibrated with empirical sensitivity coefficients ($\beta_{rate} = 0.18, \beta_{haz} = 0.16, \beta_{econ} = 0.12$).
3. **Jensen's Inequality Corrections**: Unbiased marginal expectation via $\mathbb{E}[e^{\beta \theta}] = \exp(\beta z + \frac{1}{2}\beta^2 \sigma_z^2)$.
4. **Law of Total Variance**: Formal decomposition into aleatoric Negative-Binomial dispersion ($\alpha_{bat} = 0.25, \alpha_{bowl} = 0.20$) and epistemic posterior parameter variance ($\sigma_z^2 = (RD / 350)^2$).
5. **Empirical Decile (P10) VORP Baseline**: Format-specific active replacement thresholds anchored at the uninformative prior mean for bowling.

---

### 2. Mathematical Architecture

#### 2.1 State Representation & Transformation
Every player $i$ entering match $m$ on date $T$ is characterized by pre-match state parameters strictly evaluated as of $T - 1$ day:
* Batting Rating & RD: $R_{bat, i}, RD_{bat, i} \implies z_{bat, i} = \frac{R_{bat, i} - 1000.0}{350.0}, \quad \sigma_{z,bat, i} = \frac{RD_{bat, i}}{350.0}$
* Bowling Rating & RD: $R_{bowl, i}, RD_{bowl, i} \implies z_{bowl, i} = \frac{R_{bowl, i} - 1000.0}{350.0}, \quad \sigma_{z,bowl, i} = \frac{RD_{bowl, i}}{350.0}$
* Fielding Rating & RD: $R_{field, i}, RD_{field, i} \implies z_{field, i} = \frac{R_{field, i} - 500.0}{350.0}, \quad \sigma_{z,field, i} = \frac{\max(150.0, RD_{field, i})}{350.0}$

#### 2.2 Two-Stage Batting Model
Let $Y_{runs}$ be the match runs scored by player $i$.
$$\mathbb{E}[Y_{runs}] = \mathbb{E}[B_{bat}] \cdot \mathbb{E}[\lambda_{bat}]$$

* **Stage 1 (Exposure Model)**:
  Expected balls faced $B_{bat} = g(p, F)$, where $p \in \{1, \dots, 11\}$ is batting order position and $F \in \{\text{T20}, \text{ODI}, \text{TEST}\}$:
  $$\mathbb{E}[B_{bat} \mid p, F] = \begin{cases}
  \text{T20}: & [26.5, 26.5, 20.0, 16.0, 12.0, 9.0, 6.5, 4.5, 3.0, 2.0, 1.5] \\
  \text{ODI}: & [62.0, 62.0, 48.0, 40.0, 32.0, 24.0, 18.0, 12.0, 8.0, 5.0, 3.0] \\
  \text{TEST}: & [85.0, 85.0, 80.0, 75.0, 65.0, 52.0, 42.0, 30.0, 18.0, 12.0, 8.0]
  \end{cases}$$
  If $p$ is unavailable, mapped via player role $R \in \{\text{R1}\dots\text{R8}\}$.

* **Stage 2 (Efficiency Model)**:
  Scoring rate per ball $\lambda_{bat}$:
  $$\lambda_{bat} = \lambda_0(F) \cdot \exp\left(\beta_{rate} \cdot z_{bat}\right) \cdot \left(\frac{PF}{OBQ}\right)^{\gamma}$$
  where $\lambda_0(\text{T20}) = 1.35, \lambda_0(\text{ODI}) = 0.88, \lambda_0(\text{TEST}) = 0.53$, $\beta_{rate} = 0.18$, $PF \in [0.65, 1.50]$ is park factor, and $OBQ \in [0.50, 2.00]$ is opposition bowling quality.

* **Jensen's Correction for Marginal Mean**:
  $$\mathbb{E}[Y_{runs}] = \mathbb{E}[B_{bat}] \cdot \lambda_0(F) \cdot \exp\left(\beta_{rate} z_{bat}\right) \cdot \left(\frac{PF}{OBQ}\right) \cdot \exp\left(\frac{1}{2} \beta_{rate}^2 \sigma_{z,bat}^2\right)$$

#### 2.3 Two-Stage Bowling Model
Let $W$ be wickets taken and $R_{conc}$ be runs conceded.

* **Stage 1 (Exposure Model)**:
  Expected legal balls bowled $B_{bowl} = h(Role, F)$:
  Specialists (R7/R8) bowl $22.0$ balls (T20), $52.0$ balls (ODI), $110.0$ balls (Test). Wicketkeepers (R4) bowl strictly $0.0$.

* **Stage 2 (Efficiency Model)**:
  * Wicket Hazard Rate ($h_{bowl}$):
    $$h_{bowl} = h_0(F) \cdot \exp\left(\beta_{haz} \cdot z_{bowl}\right) \cdot \left(\frac{1}{PF^{0.45} \cdot OBatQ}\right)$$
    with $h_0(\text{T20}) = 0.048, h_0(\text{ODI}) = 0.032, h_0(\text{TEST}) = 0.019$, and $\beta_{haz} = 0.16$.
    $$\mathbb{E}[W] = B_{bowl} \cdot h_{bowl} \cdot \exp\left(\frac{1}{2} \beta_{haz}^2 \sigma_{z,bowl}^2\right)$$
  * Economy Rate ($e_{bowl}$, runs per over):
    $$e_{bowl} = e_0(F) \cdot \exp\left(-\beta_{econ} \cdot z_{bowl}\right) \cdot (PF \cdot OBatQ)$$
    with $e_0(\text{T20}) = 8.10, e_0(\text{ODI}) = 5.25, e_0(\text{TEST}) = 3.15$, and $\beta_{econ} = 0.12$.
    $$\mathbb{E}[R_{conc}] = \left(\frac{B_{bowl}}{6.0}\right) \cdot e_{bowl} \cdot \exp\left(\frac{1}{2} \beta_{econ}^2 \sigma_{z,bowl}^2\right)$$

#### 2.4 Law of Total Variance & Predictive Uncertainty
By the Law of Total Variance:
$$\text{Var}_{\text{total}}(Y) = \mathbb{E}[\text{Var}(Y \mid \theta)] + \text{Var}(\mathbb{E}[Y \mid \theta])$$

For a compound Negative-Binomial count with dispersion parameter $\alpha$:
1. **Epistemic Variance**:
   $$\text{Var}_{\text{epistemic}} = \text{Var}(\mathbb{E}[Y \mid \theta]) = \hat{\mu}^2 \cdot \left(\exp(\beta^2 \sigma_z^2) - 1\right)$$
2. **Aleatoric Variance**:
   $$\mathbb{E}[\text{Var}(Y \mid \theta)] = \hat{\mu} + \alpha \cdot \mathbb{E}[(B\lambda)^2] = \hat{\mu} + \alpha \cdot \left(\hat{\mu}^2 + \text{Var}_{\text{epistemic}}\right)$$
3. **Total Variance**:
   $$\text{Var}_{\text{total}}(Y) = \left[\hat{\mu} + \alpha \hat{\mu}^2\right] + (1 + \alpha) \text{Var}_{\text{epistemic}}$$

This exact closed-form expression governs prediction interval generation (50%, 80%, 90%, 95%) and ensures calibration without heuristic padding.

---

### 3. VORP (Value Over Replacement Player) Formulation

VORP measures the marginal runs produced relative to a freely available replacement player ($R_{\text{rep}}$) under identical match exposure:

$$\text{VORP}_{total} = \text{VORP}_{bat} + \text{VORP}_{bowl} + \text{VORP}_{field}$$

* **Batting VORP**:
  $$\text{VORP}_{bat} = \mathbb{E}[Y_{runs} \mid R_{bat}] - \mathbb{E}[Y_{runs} \mid R_{\text{rep}, bat}]$$
* **Bowling VORP**:
  $$\text{VORP}_{bowl} = \left(\mathbb{E}[R_{conc} \mid R_{\text{rep}, bowl}] - \mathbb{E}[R_{conc} \mid R_{bowl}]\right) + V_{wkt} \cdot \left(\mathbb{E}[W \mid R_{bowl}] - \mathbb{E}[W \mid R_{\text{rep}, bowl}]\right)$$
* **Fielding VORP**:
  $$\text{VORP}_{field} = \left(\mathbb{E}[I_{field} \mid R_{field}] - \mathbb{E}[I_{field} \mid R_{\text{rep}, field}]\right) \cdot V_{catch}$$

#### Format Replacement Anchors (Active Experienced P10)
| Format | $R_{\text{rep}, bat}$ | $R_{\text{rep}, bowl}$ | $R_{\text{rep}, field}$ | $V_{wkt}$ (Runs) | $V_{catch}$ (Runs) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **T20** | 740.0 | 1000.0 | 600.0 | 10.5 | 3.5 |
| **ODI** | 790.0 | 1000.0 | 625.0 | 30.0 | 7.0 |
| **TEST** | 950.0 | 1000.0 | 720.0 | 45.0 | 10.0 |

* **Negative Preservation Rule**: If a player underperforms replacement level, VORP is strictly negative. Negative values are never artificially clamped to zero.

---

### 4. Implementation Reference
* Configuration: [`src/predictive/config.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/config.py)
* Uncertainty & Intervals: [`src/predictive/uncertainty.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/uncertainty.py)
* Batting Engine: [`src/predictive/batting_model.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/batting_model.py)
* Bowling Engine: [`src/predictive/bowling_model.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/bowling_model.py)
* Fielding Engine: [`src/predictive/fielding_model.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/fielding_model.py)
* VORP Engine: [`src/predictive/vorp.py`](file:///Users/divygupta/desktop/DL_DATABASE/src/predictive/vorp.py)
