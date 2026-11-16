# CricEngine AI — Known Technical & Statistical Limitations

In accordance with our core engineering principle—**"Correctness over superficial completeness / Zero fabricated data"**—this document provides an explicit and transparent audit of the known limitations, data gaps, and statistical boundaries of the CricEngine AI data lake and modeling suite (`v1.0.0`).

---

## 1. Data Source & Tournament Coverage Boundaries

### 1.1 Indian Senior Domestic Cricket (Tier 3)
- **Included:** The **Syed Mushtaq Ali Trophy (SMAT - T20)** is fully ingested (695 matches) from Cricsheet.
- **Excluded / Unavailable:**
  - **Ranji Trophy (Multi-Day / First Class):** Cricsheet does not possess ball-by-ball structured data for the Ranji Trophy.
  - **Vijay Hazare Trophy (One-Day / List-A):** Cricsheet does not possess ball-by-ball structured data for the Vijay Hazare Trophy.
  - **Other Domestic Tournaments:** Duleep Trophy, Deodhar Trophy, and Irani Cup are unavailable as open-source ball-by-ball scorecards.
- **Methodological Impact:** Player evaluations in Tier 3 rely exclusively on domestic T20 performance. First-class red-ball domestic form cannot be inferred from this dataset. We do **not** scrape unofficial third-party websites or synthesize fake multi-day scorecards.

### 1.2 Historical Chronological Horizons
- Comprehensive ball-by-ball coverage begins reliably in **2002** for Test matches and ODIs, **2005** for T20 Internationals, and **2008** for the Indian Premier League.
- Historical matches prior to 2002 lack complete ball-by-ball delivery event logs and are excluded from the canonical relational schema.

---

## 2. Sensor & Tracking Data Absence

CricEngine AI operates on official match scorecards and delivery event records, **not** optical computer vision or radar sensor feeds. The following variables are **not present** in the data lake:

1. **Hawk-Eye / Optical Tracking:** Pitch impact coordinates, bounce height, degrees of swing/seam deviation, and trajectory maps are unavailable.
2. **Radar Ball Speed:** Bowler instantaneous release speed and delivery arrival velocity (km/h or mph) are unavailable.
3. **Shot Control & Contact Quality:** "Edge", "beaten", and "control percentage" classifications are proprietary to commercial data providers (e.g. CricViz, Hawk-Eye) and absent from open scorecards.
4. **Fielder Coordinates & Reaction Times:** Exact fielding spatial positions ($X, Y$ coordinates) and sprint speeds are absent. Fielder involvement is recorded strictly through event participation (catches, stumpings, run-outs).

---

## 3. Player Demographics & Metadata Supplementation

Raw Cricsheet JSON delivery trees record player names and persistent hex IDs, but omit biographical and stylistic attributes:

- **Omitted from Source:** Batting handedness (Left/Right), bowling style (Pace/Spin, Arm), primary playing role, and date of birth.
- **Enrichment Resolution:** In Phase 3b, these attributes were supplemented by cross-referencing external official registries (`key_cricinfo`, `key_bcci`).
- **Residual Limitation:** For rare domestic players or associate international players with fewer than 5 career appearances, secondary attributes may remain categorized as `'UNKNOWN'` or inferred through empirical participation heuristics.

---

## 4. Statistical & Modeling Boundaries

### 4.1 Associate International Cricket Variance
- International T20 cricket encompasses both Tier 1 full-member nations (e.g. India, Australia, England) and Associate Member nations (e.g. Gibraltar, Turkey, Rwanda).
- While the CA-HBSS rating engine incorporates competition tier multipliers and opponent strength indices, extreme performance outliers against nascent bowling attacks can produce elevated Bayesian uncertainty bounds ($rd > 150$).

### 4.2 Modern Scoring Rate Drift (T20 Hyper-Inflation)
- Contemporary T20 cricket (e.g., IPL 2024 and onwards) has observed structural shifts in scoring velocity driven by tactical changes (e.g., Impact Player rules, aggressive powerplay utilization).
- Historical baselines and park factors calculated over long moving windows ($w = 365$ days) may exhibit slight lag in adapting to unprecedented 250+ run scoring regimes.

### 4.3 Value Over Replacement Player (VORP) Baselines
- VORP is calibrated against empirical 10th percentile replacement performance within each specific player role archetype and format.
- For niche or sparse player archetypes (e.g., left-arm wrist spin or pure batting all-rounders in Test cricket), the replacement population pool is smaller, leading to wider empirical confidence intervals on the baseline itself.

---

## 5. Intended Project Scope

CricEngine AI is designed as a **transparent, reproducible data engineering platform and academic sports analytics framework**.

- **Not a Commercial Odds Engine:** The probabilistic predictions and VORP metrics are statistical baselines designed for retrospective analysis, talent identification, and tactical research. They must **never** be used for real-time betting, wagering, or financial speculation.
- **Point-in-Time Integrity:** All feature and rating stores adhere strictly to zero-leakage, point-in-time constraints. When evaluating predictive accuracy, external practitioners must adhere to the provided chronological holdout splits.
