# CricEngine AI — Phase 3A: Player Master Enrichment Report & Acquisition Proposal

**Date**: 2026-10-30  
**Phase**: Phase 3A — Data Remediation & Enrichment  
**Milestone Finding**: `PID-04` (Missing Playing Attributes in `dim_player_master`)  
**Status**: COMPLETED WITH LIMITATIONS (Awaiting User Authorization for External Acquisition)  
**Database**: `data/datalake/curated/cricengine.duckdb` (Strictly Read-Only)  

---

## 1. Executive Summary

During the Phase 2 audit, finding **PID-04** identified that `dim_player_master` lacks fundamental player style and role attributes:
- `batting_hand` (e.g., Right-hand bat, Left-hand bat)
- `bowling_style` (e.g., Right-arm fast, Slow left-arm orthodox, Legbreak)
- `primary_role` (e.g., Opening batter, Top-order batter, Wicketkeeper-batter, Allrounder, Specialist bowler)

In accordance with explicit instructions for Phase 3A:
- **Do not scrape arbitrary websites or introduce unverified external data.**
- **If additional authoritative sources are required, document the exact data requirements and stop for approval rather than improvising.**
- **Keep unavailable attributes NULL.**
- **Do not infer a player’s primary role solely from a small number of match appearances.**

This report documents the exhaustive audit of all existing repository data assets, establishes why playing attributes cannot be reliably inferred from existing tables without fabrication, and presents a formal **Data Acquisition Specification** ready for user authorization.

---

## 2. Exhaustive Audit of Existing Repository Assets

| Source Asset | File Path | Records | Contained Fields | Coverage of Playing Attributes |
|:---|:---|:---:|:---|:---:|
| **People Registry** | `data/raw_cricsheet/registers/people.csv` | 18,683 | `identifier`, `name`, `unique_name`, `key_cricinfo`, `key_bcci`, external IDs | **0.00%** (No styles or roles) |
| **Names Registry** | `data/raw_cricsheet/registers/names.csv` | 4,204 | `identifier`, `name` | **0.00%** (Aliases only) |
| **Venues Registry** | `data/raw_cricsheet/registers/venues.csv` | 420 | `venue`, `city`, `country` | **0.00%** (Venues only) |
| **Cricsheet Raw JSON** | `data/raw_cricsheet/extracted/*/*.json` | 9,085 files | `info.players`, `info.registry`, deliveries, extras | **0.00%** (No styles or roles) |
| **Curated DuckDB** | `fact_ball_by_ball`, `fact_match_participation` | 4.38M rows | `runs_batter`, `legal_balls_bowled`, `batted_flag`, `bowled_flag` | **Observed activity only** |

### Why Behavioral Inference Is Strictly Prohibited:
1. **Handedness Cannot Be Inferred from Runs**: Observing that a player scored 45 runs off 30 balls reveals nothing about whether they bat left-handed or right-handed. Any heuristic assignment would be fabricated data.
2. **Bowling Style Cannot Be Inferred from Ball Counts**: Observing that a bowler delivered 4.0 overs with 1 maiden reveals nothing about whether they bowl right-arm off-spin, left-arm seam, or legbreak googly.
3. **Primary Role Requires Career Cohort Context**: Assigning an official playing role (e.g., "All-rounder" vs "Bowler who can bat") based on 2 or 3 associate match appearances produces severe classification bias.

Therefore, in strict compliance with the data integrity directives, all unavailable playing attributes remain **strictly `NULL`** rather than improvised.

---

## 3. Formal Data Acquisition Specification

To enrich `dim_player_master` authoritatively, an external authoritative profile dataset is required. Because Phase 3A player disambiguation ([`PHASE_3A_PLAYER_IDENTITY_REMEDIATION.md`](file:///Users/divygupta/desktop/DL_DATABASE/docs/PHASE_3A_PLAYER_IDENTITY_REMEDIATION.md)) has already mapped 100% of canonical players to their external keys, enrichment can be executed deterministically.

### A. Identifier Join Key
- **Primary Join Key**: `people.csv` `key_cricinfo`
- **Key Availability**: Exactly **6,876 out of 7,014 canonical players (98.03%)** already possess a verified ESPNcricinfo identifier.
- **Secondary Join Key**: `key_bcci` for Indian domestic fixtures without international Cricinfo coverage.

### B. Proposed Ingestion Schema: `player_playing_attributes.csv`
```csv
player_id,key_cricinfo,batting_hand,bowling_arm,bowling_type,primary_role,role_source,verified_at
ba607b88,253802,Right-hand bat,Right-arm,medium,Top-order batter,espncricinfo,2026-10-30T14:00:00Z
462411b3,625383,Right-hand bat,Right-arm,fast,Bowler,espncricinfo,2026-10-30T14:00:00Z
```

### C. Standardized Attribute Taxonomies

#### 1. `batting_hand` (Categorical ENUM)
- `Right-hand bat`
- `Left-hand bat`
- `NULL` (unverified)

#### 2. `bowling_style` (Standard ICC Classification)
- Pace: `Right-arm fast`, `Right-arm fast-medium`, `Right-arm medium-fast`, `Right-arm medium`, `Left-arm fast`, `Left-arm fast-medium`, `Left-arm medium`
- Spin: `Right-arm offbreak`, `Right-arm legbreak`, `Slow left-arm orthodox`, `Left-arm wrist spin` (unorthodox)
- `NULL` (non-bowler / unverified)

#### 3. `primary_role` (Standard ESPNcricinfo Cohort Classification)
- `Opening batter`
- `Top-order batter`
- `Middle-order batter`
- `Wicketkeeper-batter`
- `Allrounder`
- `Bowling allrounder`
- `Bowler`
- `NULL` (unverified)

---

## 4. Proposed Migration Plan (Awaiting Authorization)

Once the user approves the acquisition of the authoritative ESPNcricinfo profile dataset:
1. Stage the raw CSV artifact into `data/raw_external/cricinfo_player_profiles.csv`.
2. Compute SHA-256 and byte size manifests.
3. In a separate authorized milestone, alter `dim_player_master` or create an enriched curated view `v_player_master_enriched`.
4. Validate that zero canonical `player_id`s are modified or dropped.

---

## 5. Conclusion & Gate Status

Finding **PID-04** is classified as **COMPLETED WITH LIMITATIONS**. The limitation is explicitly bounded, existing attributes remain unpolluted by fabricated guesses, and the complete data acquisition specification is prepared for future milestone approval.
