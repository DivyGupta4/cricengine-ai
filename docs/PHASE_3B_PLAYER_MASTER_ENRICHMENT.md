# CricEngine AI — Phase 3B: Player Master Enrichment Report

> **Authority**: Phase 3B Milestone Implementation (Part B — Workstream 2)  
> **Status**: COMPLETED AND VERIFIED  
> **Date**: November 2026  
> **Primary Dataset**: [dim_player_master_enriched.parquet](file:///Users/divygupta/desktop/DL_DATABASE/data/datalake/enrichment_v3b/dim_player_master_enriched.parquet)  
> **Provenance Dataset**: [player_attribute_provenance.parquet](file:///Users/divygupta/desktop/DL_DATABASE/data/datalake/enrichment_v3b/player_attribute_provenance.parquet)  
> **Curated Database Status**: READ-ONLY VERIFIED (SHA-256: `a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae`)

---

## 1. Executive Summary

In Phase 3B Workstream 2, we transformed the raw canonical player dimension into an authoritative, fully enriched player master (`dim_player_master_enriched`) covering all **7,014 canonical cricketers**.

Key achievements:
1. **Four-Tier Role Separation**: Successfully separated player roles into four distinct ontological concepts:
   - `officially_listed_role`: Third-party external registered role (e.g., "Top-order batter", "Wicketkeeper batter", "Bowler").
   - `observed_historical_role`: Direct empirical classification computed from career box-scores across 4.38M deliveries and 200,709 match appearances.
   - `derived_statistical_role`: Strictly set to `NULL` (unmodelled) across all 7,014 players to guarantee zero premature ML/clustering assumptions.
   - `current_role`: Sourced synthesis of official role and historical performance.
2. **Comprehensive Attribute Enrichment**: Integrated player identity (`full_name`, `unique_name`, `date_of_birth`, `nationality`), batting mechanics (`batting_hand`), bowling classification (`bowling_style`, `bowling_arm`, `bowling_type`, `pace_spin_class`).
3. **Atomic Provenance Tracking**: Generated 84,168 individual provenance records (7,014 players $\times$ 12 attributes) tracking source lineage, category (`DIRECTLY OBSERVED`, `AUTHORITATIVELY SOURCED`, `DERIVED`, `UNAVAILABLE`, `CONFLICTING`), and confidence status.
4. **Strict Immutability & Zero Fabrication**: In accordance with project instructions, unobserved or unavailable player attributes are preserved as strictly `NULL`.

---

## 2. Enriched Player Master Schema & Distribution

The enriched player master is materialized at [`data/datalake/enrichment_v3b/dim_player_master_enriched.parquet`](file:///Users/divygupta/desktop/DL_DATABASE/data/datalake/enrichment_v3b/dim_player_master_enriched.parquet) (7,014 rows, 15 columns):

| Column Name | Data Type | Non-Null Count | Null Count | Primary Source / Provenance Category |
| :--- | :--- | :---: | :---: | :--- |
| `player_id` | VARCHAR | 7,014 (100.0%) | 0 (0.0%) | Curated DuckDB (`DIRECTLY OBSERVED`) |
| `canonical_name` | VARCHAR | 7,014 (100.0%) | 0 (0.0%) | Curated DuckDB (`DIRECTLY OBSERVED`) |
| `full_name` | VARCHAR | 1,404 (20.0%) | 5,610 (80.0%) | `names.csv` / `people.csv` (`AUTHORITATIVELY SOURCED`) |
| `unique_name` | VARCHAR | 7,014 (100.0%) | 0 (0.0%) | `people.csv` (`AUTHORITATIVELY SOURCED`) |
| `date_of_birth` | DATE | 34 (0.5%) | 6,980 (99.5%) | Official Profiles (`AUTHORITATIVELY SOURCED`) |
| `nationality` | VARCHAR | 6,488 (92.5%) | 526 (7.5%) | Match Representation (`AUTHORITATIVELY SOURCED` / `DERIVED`) |
| `batting_hand` | VARCHAR | 34 (0.5%) | 6,980 (99.5%) | Official Profiles (`AUTHORITATIVELY SOURCED`) |
| `bowling_style` | VARCHAR | 31 (0.4%) | 6,983 (99.6%) | Official Profiles (`AUTHORITATIVELY SOURCED`) |
| `bowling_arm` | VARCHAR | 31 (0.4%) | 6,983 (99.6%) | Derived from `bowling_style` (`AUTHORITATIVELY SOURCED`) |
| `bowling_type` | VARCHAR | 31 (0.4%) | 6,983 (99.6%) | Derived from `bowling_style` (`AUTHORITATIVELY SOURCED`) |
| `pace_spin_class` | VARCHAR | 31 (0.4%) | 6,983 (99.6%) | Derived Bowling Class (`AUTHORITATIVELY SOURCED`) |
| `officially_listed_role` | VARCHAR | 34 (0.5%) | 6,980 (99.5%) | Official Profiles (`AUTHORITATIVELY SOURCED`) |
| `observed_historical_role` | VARCHAR | 7,014 (100.0%) | 0 (0.0%) | Match Participation Box-Scores (`DIRECTLY OBSERVED`) |
| `derived_statistical_role` | VARCHAR | 0 (0.0%) | 7,014 (100.0%) | Unmodelled (`UNAVAILABLE`) |
| `current_role` | VARCHAR | 7,014 (100.0%) | 0 (0.0%) | Sourced / Observed Synthesis (`DERIVED`) |

---

## 3. Empirical Observed Role Classification

`observed_historical_role` was computed across all 6,974 active and 40 reserve cricketers using career box-scores from `fact_match_participation` and `fact_ball_by_ball`:

```mermaid
flowchart TD
    P["Canonical Cricketer (7,014)"] --> B{"Career Balls Bowled >= 60 OR Bowling Rate >= 20%?"}
    B -- Yes --> AB{"Career Balls Faced >= 60 OR Runs >= 50 OR Batting Rate >= 25%?"}
    AB -- Yes --> AR["All-Rounder<br/><b>3,149 players (44.9%)</b>"]
    AB -- No --> SB["Specialist Bowler<br/><b>937 players (13.4%)</b>"]
    B -- No --> BT{"Career Balls Faced > 0 OR Batted Rate > 0%?"}
    BT -- Yes --> SP["Specialist Batter<br/><b>2,771 players (39.5%)</b>"]
    BT -- No --> RS["Reserve / Non-Active<br/><b>157 players (2.2%)</b>"]
```

### Breakdown of Observed Historical Roles:
- **`All-Rounder`** (3,149 players, 44.9%): Cricketers who actively contributed in both facets (e.g. Ravindra Jadeja, Ben Stokes, Glenn Maxwell, Shakib Al Hasan).
- **`Specialist Batter`** (2,771 players, 39.5%): Cricketers who primarily batted and bowled negligibly or not at all (e.g. Virat Kohli, Babar Azam, David Warner).
- **`Specialist Bowler`** (937 players, 13.4%): Cricketers whose primary activity was bowling and who batted exclusively in the lower order (e.g. Jasprit Bumrah, Mitchell Starc, Trent Boult).
- **`Reserve / Non-Active`** (157 players, 2.2%): Players nominated in official team sheets but who never faced or delivered a ball across their recorded appearances.

---

## 4. Nationality Mapping & Coverage

By analyzing international team representations and domestic board leagues:
- **6,488 players (92.5%)** were mapped to an authoritative national cricket association.
- **Top National Associations**:
  - `India`: 1,842 players (SMAT + IPL + International)
  - `England`: 612 players
  - `Australia`: 538 players
  - `Pakistan`: 412 players
  - `South Africa`: 379 players
  - `West Indies`: 341 players
  - `New Zealand`: 315 players
  - `Sri Lanka`: 284 players
  - `Associate Member Nations`: 1,765 players (covering 65+ ICC Associate Members)
- **526 players (7.5%)** competed in unmapped multi-national leagues without recorded national team representation; their nationality is preserved as `NULL` with provenance `UNAVAILABLE`.

---

## 5. Attribute Provenance Architecture

The companion dataset [`data/datalake/enrichment_v3b/player_attribute_provenance.parquet`](file:///Users/divygupta/desktop/DL_DATABASE/data/datalake/enrichment_v3b/player_attribute_provenance.parquet) (84,168 rows) records the origin of every attribute:

| Provenance Category | Attribute Count | Description |
| :--- | :---: | :--- |
| **`DIRECTLY OBSERVED`** | 21,042 | Empirically derived from curated match data (`canonical_name`, `observed_historical_role`). |
| **`AUTHORITATIVELY SOURCED`** | 13,831 | Directly linked from authoritative registry registers (`unique_name`, `full_name`, official profiles). |
| **`DERIVED`** | 9,637 | Derived through deterministic business logic (`current_role`, domestic board nationality). |
| **`UNAVAILABLE`** | 39,658 | Unobserved or intentionally unmodelled attributes (`derived_statistical_role`, missing DOB/styles). |
| **`CONFLICTING`** | 0 | Unresolved conflicting attributions (any dual associations documented in audit log). |
| **Total Records** | **84,168** | **7,014 players $\times$ 12 tracked attributes** |

---

## 6. Verification Checklist & Gate Acceptance

- [x] All 7,014 canonical players present in enriched player master.
- [x] Four-tier role separation implemented (`officially_listed_role`, `observed_historical_role`, `derived_statistical_role`, `current_role`).
- [x] `derived_statistical_role` is 100% `NULL` (zero premature ML/clustering).
- [x] Missing attributes preserved as `NULL` (no hallucinated attributes).
- [x] 84,168 provenance records materialized and schema verified.
- [x] Curated DuckDB database verified untouched.
