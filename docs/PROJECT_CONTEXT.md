# CricEngine AI — Project Context & Master System Architecture

## 1. Executive Summary & Objective

**CricEngine AI** is an end-to-end, deep-learning-driven cricket analytics, dynamic player rating, and Playing XI optimization engine designed to evaluate Indian male cricketers across formats and competition levels. 

Conventional cricket metrics (such as unadjusted batting averages, strike rates, and bowling economy rates) fail to reflect true player contribution due to situational confounders:
- **Phase Context**: Scoring at 140 SR in the Powerplay vs. Death overs represents fundamentally different difficulty and risk profiles.
- **Wicket Value**: Dismissing a top-order anchor has vastly greater win-equity impact than dismissing a tailender.
- **Surface & Venue Context**: High-scoring flat tracks vs. turning or swinging pitches dramatically alter benchmark expectations.
- **Competition Quality**: Differences in opposition caliber between International cricket, the Indian Premier League (IPL), and Senior Domestic tournaments (Syed Mushtaq Ali Trophy, Ranji Trophy, Vijay Hazare Trophy).
- **Recency vs. Established Class**: Form decays and fluctuates, requiring temporal models that weight recent performances without wiping out established career priors.
- **Partnership & Bowling Synergies**: Complementary bowling pairings (pace-spin pressure) and batting pair dynamics (left-right balance, strike-rotation chemistry) influence match outcomes beyond isolated individual statistics.

The system is intended to support evidence-based selection for the Indian Men’s National Cricket Team across all three formats: **Test Matches**, **One Day Internationals (ODIs)**, and **Twenty20 Internationals (T20Is)**.

---

## 2. End-to-End System Architecture

The overarching system is partitioned into five distinct stages:

```
[ Stage 1: Data Ingestion & Feature Store ]
  ├── Cricsheet JSON & Register Ingestion
  ├── Relational Storage (DuckDB + Parquet)
  ├── Data Quality & Validation Engine
  ├── Target Player Cohort Extraction
  └── Dynamic Rolling Feature Store
             │
             ▼
[ Stage 2: Dynamic Player Rating Engine ]
  ├── Neural Elo / Glicko Rating Updates
  ├── Temporal Fusion Transformers (TFTs)
  └── Graph Neural Networks (GNNs) for Synergies
             │
             ▼
[ Stage 3: Playing XI Optimization Engine ]
  ├── Mixed-Integer Linear Programming (MILP)
  ├── Squad Composition & Role Constraints
  └── Venue / Opposition / Pitch Condition Conditioning
             │
             ▼
[ Stage 4: Human-in-the-Loop Selector Dashboard ]
  ├── Scenario Simulation & Selection Overrides
  └── Explainable AI (SHAP Attributions)
             │
             ▼
[ Stage 5: Continuous Ingestion & Retraining ]
  └── Incremental Data Updates & Scheduled Model Refreshes
```

### Stage 1: Multi-Tier Data Ingestion and Feature Store *(Current Scope: Phase 1)*
Collect, normalize, validate, and organize delivery-level and match-level cricket data across three competition tiers:
- **Tier 1 (International)**: Tests, ODIs, T20Is.
- **Tier 2 (Franchise)**: Indian Premier League (IPL).
- **Tier 3 (Senior Domestic)**: Syed Mushtaq Ali Trophy (SMAT), plus Ranji Trophy and Vijay Hazare Trophy where structured data exists.
- **Core Storage**: Local embedded DuckDB database + partitioned Apache Parquet analytical data lake.

### Stage 2: Dynamic Player Rating Engine *(Future Phase)*
- Contextual rating that updates after every match/delivery.
- Separation of long-term intrinsic baseline ability from transitory form.
- Modeling temporal sequences via Temporal Fusion Transformers (TFT).
- Modeling player interaction networks via Graph Neural Networks (GNN).
- Competition-tier quality adjustments (e.g., performance discounts/premiums across domestic vs. international matches).

### Stage 3: Playing XI Optimization *(Future Phase)*
- Formulation as a constrained Mixed-Integer Linear Programming (MILP) problem (and potential DRL exploration).
- Objective: Maximize projected team match equity subject to hard cricket constraints:
  - Exactly 11 players;
  - At least 1 designated wicketkeeper;
  - Minimum quota of bowling options (e.g., at least 5 viable bowlers spanning required overs);
  - Balance of pace vs. spin dictated by venue/pitch characteristics;
  - Batting order construction (openers, middle order, finishers) and handedness diversification;
  - Partnership and bowling pair synergy optimization;
  - Workload and injury availability filters.

### Stage 4: Human-in-the-Loop Selection Dashboard *(Future Phase)*
- Tactical workbench for selectors, analysts, and coaches.
- Input assumptions: match venue, expected pitch type, weather, opponent lineup.
- SHAP (SHapley Additive exPlanations) visualizations explaining why a player is recommended or omitted.
- Manual override capability: allowing human selectors to pin specific players and re-optimize the remaining slots.

### Stage 5: Continuous Data and Model Updates *(Future Phase)*
- Automated match-day ingestion pipelines.
- Incremental player rating drift and form updates.
- Automated pipeline execution and monitoring.

---

## 3. Current Scope: Phase 1 Foundation

Phase 1 focuses exclusively on establishing a reliable, reproducible, and verifiable engineering foundation. **No machine learning models or optimization solvers will be trained in Phase 1.**

### Core Relational Tables & Evaluated Extensions

The local analytical lake is structured into core canonical tables in DuckDB and Parquet:

| Table Name | Entity Type | Grain / Primary Key | Description & Relationships |
| :--- | :--- | :--- | :--- |
| `dim_player_master` | Dimension | `player_id` | Canonical player entity: stable internal UUID/hash, canonical full name, DOB, nationality, eligibility, primary role, taxonomic subrole, batting hand, bowling style. Nullable fields are preserved as true SQL NULL. |
| `player_source_identity` | Mapping | `(source_system, source_player_id)` | Maps source-specific identifiers (Cricsheet ID, ESPN Cricinfo ID, BCCI ID, Pulse ID) and aliases to the canonical `player_id`. Preserves audit status (verified, ambiguous, manual_review). |
| `dim_match` | Dimension | `match_id` | Match-level canonical entity: date, season, match type/format, competition name, competition tier, teams involved, gender. |
| `dim_match_context` | Dimension | `match_id` | Environmental match context: venue name, city, toss winner, toss decision, outcome (winner, win margins, eliminator/super over flag), officials. Explicit NULLs for unobserved surface/boundary metrics. |
| `fact_match_participation` | Fact | `participation_id` | Player appearance record: `player_id`, `match_id`, match date, team, confirmed playing XI flag vs squad bench, days since last match. |
| `fact_innings` | Fact | `innings_id` | Innings-level summary: `match_id`, `innings_num`, batting team, bowling team, total runs, total extras, total wickets, total legal overs, target runs (if applicable). Reconciles ball-by-ball totals against scoreboard facts. |
| `fact_ball_by_ball` | Fact | `ball_id` | Delivery event: `match_id`, `innings`, `over_num`, `delivery_num`, `match_phase`, batter (`player_id`), bowler (`player_id`), non-striker (`player_id`), runs (batter, extras breakdown, total), legal ball flag, wicket flag, dismissal type, dismissed player ID, fielders. Contains strictly directly observed facts. |
| `fact_pairwise_synergy_matrix` | Fact / Edge | `synergy_id` | Pairwise player relationship edge table (`player_a_id`, `player_b_id`, format, synergy metrics). Kept unpopulated in Phase 1 until statistical calculation methodology is implemented. |
| `data_source_manifest` | Operational | `manifest_id` | Provenance log: source archive name, source URL, download timestamp, file hash/checksum, match count reported, match count ingested, processing status. |
| `data_quality_results` | Operational | `check_id` | Ingestion validation audit log: check name, target table, records evaluated, failures detected, status (PASS, WARNING, FAIL), executed timestamp. |

*Downstream Analytical Output:*
- `dim_player_feature_store`: Rolling performance feature table (form over L5, L10, L20 matches strictly prior to match date, format splits, phase splits), treated as an analytical output separate from raw ingestion.

### Metric Classification Taxonomy
To maintain architectural hygiene and prevent fabricated data, all metrics are classified into four mutually exclusive categories:
1. **Directly Observed**: Captured directly from source delivery events (runs, extras, wickets, batter, bowler, venue, toss).
2. **Deterministically Derived**: Computed via deterministic mathematical/counting rules without free parameters (strike rate = runs/balls*100, economy rate = runs/overs, dot ball %, boundary %).
3. **Model-Generated**: Dependent on a trained machine learning model (xRA, xW, win probability delta, player ratings, shot control flags). **Explicitly out of scope for Phase 1.**
4. **External Dependent**: Requires an external authoritative dataset (exact pitch soil type, Hawkeye optical turn degrees, laser boundary measurements). **Explicitly out of scope for Phase 1.**

### Canonical Player Identity Strategy
- Internal canonical `player_id`: Stable identifier independent of display names or external changes.
- Cricsheet hex hashes (e.g. `252938a6`) serve as initial canonical keys, cross-referenced via `player_source_identity`.
- Multiple name aliases (e.g. "V Kohli", "Virat Kohli") resolve deterministically through `player_source_identity`.
- Ambiguous name matches are flagged for manual review rather than silently merged.

### Temporal Correctness & Rolling Feature Windows
- **Cutoff Convention**: For any match $M_t$ played on date $D_t$, rolling features strictly use qualifying matches played on dates $D < D_t$. Zero lookahead data is permitted.
- **Window Units**: L5, L10, L20 represent the last $N$ qualifying **matches** where the player was in the confirmed Playing XI. Innings-specific filters (e.g., innings where player actually batted or bowled) are maintained as explicit sub-aggregations.
- **Format Specificity**: Form is aggregated strictly within format (Test L5/10/20, ODI L5/10/20, T20 L5/10/20) to prevent distortion from format differences.

### Target Player Cohort Specification
- **Cohort**: Active male Indian cricketers.
- **Time Window**: Qualifying senior-level match activity on or after **1 January 2020**.
- **Competitions**: Tier 1 (Internationals), Tier 2 (IPL), Tier 3 (Syed Mushtaq Ali Trophy).
- **Activity Threshold**: Minimum of **5 distinct qualifying matches** post-2020.
- **Metadata Integrity**: Flags players with unverified nationality, gender, or role instead of fabricating attributes.


---

## 4. Engineering Principles & Non-Negotiables

1. **No Data Fabrication**: Never fabricate missing dates of birth, bowling styles, pitch measurements, or advanced metrics. If an attribute is missing in source data, record explicit `NULL` and flag for supplemental resolution.
2. **Inspect Before Implementing**: Inspect raw files, schemas, and API responses before writing production transformations.
3. **Reproducibility & Idempotency**: Ingestion must be deterministic. Rerunning pipelines must not duplicate data or alter keys.
4. **Source Provenance**: Every row in the relational model must be traceable to its original Cricsheet source archive and file.
5. **No Heavy Infrastructure**: Strictly utilize local, zero-server analytical tools: Python, DuckDB, Parquet, and PyArrow.
6. **No Future-Data Leakage**: Rolling feature windows must strictly aggregate past matches relative to match date.
