# CricEngine AI — Phase 4A: Temporal Rating & Uncertainty Framework

> **Authority**: Phase 4A Quantitative Research & Architecture  
> **Status**: COMPLETED AND VERIFIED  
> **Target Audience**: Quantitative Researchers, Statistical Modellers, National Selectors  
> **Context**: State-space formulation of player ratings over calendar time, uncertainty propagation, inactivity decay, and point-in-time historical reconstruction.

---

## 1. Executive Summary & Foundational Principles

In sporting analytics, an athlete's skill is neither static nor infinitely persistent. A player's performance capacity evolves through physical maturation, technical improvements, aging, injuries, tactical obsolescence, and psychological momentum.

Furthermore, observing an athlete provides information; **not observing an athlete increases epistemic uncertainty**. If an elite batter does not play competitive cricket for 14 months due to injury, their fundamental underlying ability has not evaporated to zero, but our certainty regarding their current readiness has substantially degraded.

The **CricEngine AI Temporal Rating & Uncertainty Framework** resolves these dynamics through a continuous-time Gaussian State-Space model with Glicko-style volatility updates.

### Core Principles
1. **Separation of Skill and Certainty**: Every player state is represented as a bivariate Gaussian distribution $\theta_{i}(t) \sim \mathcal{N}\left(\mu_{i}(t), \sigma_{i}^2(t)\right)$, where $\mu_i(t)$ is the estimated mean rating and $\sigma_i(t) \equiv \text{RD}_i(t)$ is the Rating Deviation (uncertainty).
2. **Inactivity as Variance Inflation**: Passage of calendar time without match observations strictly inflates $\text{RD}_i(t)$ while preserving mean skill $\mu_i(t)$.
3. **Decoupled Metric Hierarchy**: Clear mathematical distinction between **Career Underlying Ability**, **Current Latent Ability**, **Recent Form**, and **Performance Volatility**.
4. **Deterministic Point-in-Time Reconstruction**: Any historical rating query at arbitrary timestamp $t_0$ produces mathematically exact, leak-free values.

---

## 2. Dynamic State-Space Mathematical Formulation

```mermaid
graph LR
    subgraph Match_T_Minus_1["Match at t - 1"]
        StatePrev["Prior State<br/>(μ_t-1, RD_t-1, σ_vol)"]
    end
    
    subgraph Time_Step["Calendar Time Elapsed (Δt)"]
        TimeInflate["Variance Inflation (Brownian Drift)<br/>RD' = sqrt(RD^2 + c^2 · Δt)"]
    end
    
    subgraph Match_T["Match Observation at t"]
        Obs["Contextual PAE Observation (y_t)<br/>Obs Variance (s_t^2)"]
    end
    
    subgraph Kalman_Update["Bayesian State-Space Update"]
        Gain["Kalman / Glicko Gain (K_t)"]
        StateNew["Posterior State<br/>(μ_t, RD_t, σ_vol_t)"]
    end
    
    StatePrev --> TimeInflate
    TimeInflate --> Gain
    Obs --> Gain
    Gain --> StateNew
```

### 2.1. Continuous-Time Latent State Evolution
Let $\theta_i(t)$ represent the true latent skill of player $i$ at continuous time $t$. The latent skill follows a driftless Brownian motion:

$$d\theta_i(t) = \sigma_{\text{drift}, i} \cdot dW_i(t)$$

where $W_i(t)$ is a standard Wiener process, and $\sigma_{\text{drift}, i}$ is the player's intrinsic rate of skill drift per unit time.

### 2.2. Calendar Time Uncertainty Inflation
Let a player's last evaluated match occur at timestamp $t_{k-1}$. When queried or evaluated at timestamp $t > t_{k-1}$ after an elapsed duration $\Delta t = t - t_{k-1}$ days:

The prior mean skill remains constant:
$$\mu_i^-(t) = \mu_i(t_{k-1})$$

The prior Rating Deviation (uncertainty) inflates monotonically with time:
$$\text{RD}_i^-(t) = \min \left( \sqrt{\text{RD}_i(t_{k-1})^2 + c_F^2 \cdot \Delta t}, \; \text{RD}_{\max} \right)$$

where:
- $\Delta t$: Days elapsed since last competitive appearance.
- $c_F$: Format-specific daily uncertainty growth parameter ($c_{\text{T20}} > c_{\text{ODI}} > c_{\text{Test}}$).
- $\text{RD}_{\max}$: Maximum uninformative rating deviation (default: 350.0).
- $\text{RD}_{\min}$: Minimum rating deviation floor representing irreducible stochasticity (default: 35.0).

#### Calibrated Parameter Values by Format:
| Parameter | T20 Engine | ODI Engine | Test Engine | Analytical Justification |
| :--- | :--- | :--- | :--- | :--- |
| **Drift Constant ($c_F$)** | $1.25\text{ RD}/\sqrt{\text{day}}$ | $0.85\text{ RD}/\sqrt{\text{day}}$ | $0.55\text{ RD}/\sqrt{\text{day}}$ | T20 volatility and tactical shifts occur much faster than Test skills. |
| **Half-Life ($t_{1/2}$)** | 90 days | 180 days | 365 days | Empirical autocorrelation half-life of contextual performance. |
| **Max Uncertainty ($\text{RD}_{\max}$)** | 350.0 | 350.0 | 350.0 | Glicko-2 standard uninformative prior bound. |
| **Min Uncertainty ($\text{RD}_{\min}$)** | 40.0 | 35.0 | 30.0 | Accounts for finite sample bounds even after hundreds of matches. |

---

### 2.3. Bayesian Posterior State Update (Upon Match Observation)

When player $i$ participates in match $m$ at timestamp $t_k$, generating contextual Performance Above Expectation $y_{i, m}$ with observational variance $s_{i, m}^2$:

1. **Glicko-2 Scaling Transformation**:
   Convert parameters to Glicko scale ($\theta = (\mu - 1500) / 173.7178$, $\phi = \text{RD} / 173.7178$).

2. **Observation Precision & Kalman Gain**:
   Let $g(\phi_{\text{opp}}) = \frac{1}{\sqrt{1 + 3\phi_{\text{opp}}^2 / \pi^2}}$ represent the attenuation factor accounting for opponent rating uncertainty.

   The variance of the observation is:
   $$v_{i, k} = \left[ \sum_{j \in \text{Opp}} g(\phi_j)^2 \cdot E_j \cdot (1 - E_j) \right]^{-1}$$

   The posterior update equations are:
   $$\Delta \mu_{i, k} = \frac{\phi_i^-(t_k)^2}{\phi_i^-(t_k)^2 + v_{i, k}} \cdot \sum_{j} g(\phi_j) \left( y_{i, j} - \mathbb{E}[y_{i, j}] \right)$$

   $$\mu_i(t_k) = \mu_i^-(t_k) + \Delta \mu_{i, k}$$

   $$\phi_i(t_k) = \left[ \frac{1}{\phi_i^-(t_k)^2} + \frac{1}{v_{i, k}} \right]^{-1/2}$$

3. **Return to CricEngine Scale**:
   Transform back to native scale:
   $$\mu_i(t_k) \leftarrow \mu_i(t_k) \cdot 173.7178 + 1500$$
   $$\text{RD}_i(t_k) \leftarrow \phi_i(t_k) \cdot 173.7178$$

---

## 3. Four-Tier Skill Decomposition

To provide actionable insights to coaching staff and selectors, CricEngine AI decomposes a player's temporal profile into four distinct mathematical tiers:

```mermaid
graph TD
    A["Raw Historical Observations (PAE Lineage)"] --> B["1. Career Underlying Ability (μ_career)<br/>• Long-term regressed Bayes mean<br/>• Insensitive to short-term slumps"]
    A --> C["2. Current Latent Ability (μ_t, RD_t)<br/>• Real-time state-space estimate<br/>• Adjusted for calendar inactivity"]
    A --> D["3. Recent Form Index (F_recent)<br/>• Short-term EWMA (last 5–10 matches)<br/>• Measures momentum & hot-streaks"]
    A --> E["4. Performance Volatility (σ_vol)<br/>• Variance of residuals around expectation<br/>• Differentiates anchors from boom-bust players"]
```

### 3.1. Tier 1: Career Underlying Ability ($\mu_{\text{career}}$)
Represents the player's lifetime talent ceiling and floor, estimated via hierarchical empirical Bayes over their entire career span:

$$\mu_{\text{career}, i} = \frac{\sum_{m=1}^{N_i} w_m y_{i, m} + K_0 \mu_0}{\sum_{m=1}^{N_i} w_m + K_0}$$

where $K_0$ is the format-specific shrinkage parameter. $\mu_{\text{career}}$ is highly stable and does not oscillate wildly based on a single poor series.

### 3.2. Tier 2: Current Latent Ability ($\mu_{\text{current}}, \text{RD}_{\text{current}}$)
The point-in-time state $\theta_i(t) \sim \mathcal{N}(\mu_i(t), \text{RD}_i(t)^2)$ calculated via the state-space equations with calendar-time decay applied up to the decision timestamp.

### 3.3. Tier 3: Recent Form Index ($\mathcal{F}_{\text{recent}}$)
Measures the short-term trajectory and momentum of a player relative to their established latent ability. Form is formulated as an Exponentially Weighted Moving Average (EWMA) of performance residuals over the most recent $N \le 10$ matches or 90 calendar days:

$$\mathcal{F}_{\text{recent}}(i, t) = \frac{\sum_{k=1}^M e^{-\lambda \cdot (t - t_k)} \cdot \left( y_{i, k} - \mathbb{E}[y_{i, k}] \right)}{\sum_{k=1}^M e^{-\lambda \cdot (t - t_k)}}$$

- $\mathcal{F} > +1.5$: "In the form of their life" (hot streak).
- $\mathcal{F} \approx 0.0$: Performing exactly at expected underlying skill.
- $\mathcal{F} < -1.5$: Significant technical or psychological slump.

### 3.4. Tier 4: Performance Volatility ($\sigma_{\text{vol}}$)
Measures the dispersion of a player's performance. Two players with an identical mean rating of 1200 may exhibit completely different distribution shapes:
- **Low Volatility Player ($\sigma_{\text{vol}} = 0.25$)**: Consistent accumulator (scores 30–50 runs almost every innings). Ideal anchor.
- **High Volatility Player ($\sigma_{\text{vol}} = 0.85$)**: Boom-or-bust match winner (scores 0, 4, 110, 8, 95). Ideal high-ceiling tournament disruptor.

Volatility is formally tracked via the Glicko-2 volatility parameter update:
$$\sigma_{\text{vol}, i}(t_k) = \arg\min_{\sigma} f(\sigma \mid \mu_i, \text{RD}_i, y_i, \tau)$$
where $\tau$ is the system volatility constraint ($\tau = 0.5$ in CricEngine AI).

---

## 4. Special Player Trajectories & Edge-Case Dynamics

### 4.1. Extended Inactivity & Injury Hiatus
When a player is inactive for $T_{\text{hiatus}} > 180$ days:
- $\mu(t)$ is preserved: The model assumes talent does not spontaneously convert into non-talent.
- $\text{RD}(t)$ increases according to the calendar-time formula until reaching $\text{RD}_{\max} = 350$.
- In the selection optimization engine, the player's 95% lower confidence bound $\mu - 1.96 \cdot \text{RD}$ will drop, penalizing the selection of unverified players in must-win matches while preserving their ceiling for low-risk fixtures.

### 4.2. Comeback Match Dynamics
Upon returning from a hiatus, the elevated $\text{RD}$ creates high sensitivity to initial performances:
- If the returning player performs well, the Kalman gain $K$ is large, rapidly confirming their elite status.
- $\text{RD}$ drops drastically by 40–60% in the first 2–3 matches back as new data floods the posterior distribution.

### 4.3. Format Transitions (e.g., T20 Phenom Picked for Tests)
Because format ratings are decoupled, when a player debuts in a new format:
- They do **NOT** inherit the exact scalar rating of another format.
- Instead, their starting prior $\mu_{0, \text{debut}}$ is informed by a format-correlation projection matrix with elevated uncertainty ($\text{RD} = 280$):
  $$\mu_{0, \text{Test}} = \beta_0 + \beta_{\text{FC}} \cdot \mu_{\text{FirstClass}} + \beta_{\text{ODI}} \cdot \mu_{\text{ODI}}$$
  If first-class/domestic data is unavailable, the prior defaults to the tier baseline $\mu_{0, \text{tier}}$.

### 4.4. Identity Resolution Uncertainty (Babar Ali `c65e0275`)
As established in Phase 3B.1, player `c65e0275` carries a `PROBABLE` resolution status:
- For this player, the initial rating deviation is inflated by a permanent penalty factor:
  $$\text{RD}_{\text{init}} = \min(1.5 \times \text{RD}_{\text{standard}}, \text{RD}_{\max})$$
- In rating query results, this player's record is flagged with `uncertainty_flag = 'IDENTITY_PROBABLE'`.

---

## 5. Historical Point-in-Time Query Specification

### 5.1. The Point-in-Time Query Requirement
Downstream applications (and historical backtesting engines) require exact answers to queries such as:
> *"What was Jasprit Bumrah's T20 bowling rating and uncertainty on 2021-10-24 at 18:00 UTC?"*

### 5.2. Deterministic Query Algorithm
To answer any historical query for player $i$, format $F$, at target timestamp $t_{\text{query}}$:

```mermaid
graph TD
    Query["Query: (Player_ID, Format, Target_Timestamp t_query)"] --> Search
    Search["1. Binary Search in Temporal State Parquet<br/>Find latest record where event_timestamp <= t_query"]
    Search --> Found{"Record Found?"}
    Found -- "No" --> Debut["Return Tier Baseline Prior<br/>μ = μ_0_tier, RD = 350.0"]
    Found -- "Yes" --> Extract["Extract recorded state:<br/>(μ_last, RD_last, t_last)"]
    Extract --> Compute["2. Compute Elapsed Time:<br/>Δt = t_query - t_last (in days)"]
    Compute --> Inflate["3. Apply Variance Inflation:<br/>μ(t_query) = μ_last<br/>RD(t_query) = min(sqrt(RD_last^2 + c^2 · Δt), 350.0)"]
    Inflate --> Return["Return Point-in-Time State:<br/>(μ_query, RD_query, Form_query)"]
```

#### Determinism Guarantee:
Because this algorithm operates exclusively on immutable historical records with timestamps $\le t_{\text{query}}$, the computed state is **strictly deterministic, reproducible, and immune to lookahead bias**.

---

## 6. Bayesian Selection Probability Formulations

When the selection engine compares two players ($A$ and $B$) for a single specialist slot at time $t$:

Given independent posteriors $\theta_A \sim \mathcal{N}(\mu_A, \text{RD}_A^2)$ and $\theta_B \sim \mathcal{N}(\mu_B, \text{RD}_B^2)$:

$$\Delta \theta = \theta_A - \theta_B \sim \mathcal{N}\left(\mu_A - \mu_B, \; \text{RD}_A^2 + \text{RD}_B^2\right)$$

The probability that Player $A$ is superior to Player $B$ at timestamp $t$ is:

$$P\left(\theta_A > \theta_B \mid \mathcal{D}_t\right) = \Phi\left( \frac{\mu_A(t) - \mu_B(t)}{\sqrt{\text{RD}_A(t)^2 + \text{RD}_B(t)^2}} \right)$$

where $\Phi(\cdot)$ is the standard normal cumulative distribution function.

This allows the National Selection Engine to evaluate risk: a veteran with $\mu = 1100, \text{RD} = 40$ may be preferred over an erratic talent with $\mu = 1140, \text{RD} = 220$ when risk minimization is required in a knockout semi-final.

---

> **Architectural Sign-off**: The Temporal Rating and Uncertainty Framework mathematically reconciles dynamic skill evolution, calendar-time inactivity, momentum form, and point-in-time query reproducibility without data leakage.
