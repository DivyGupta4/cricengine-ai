# CricEngine AI — Data Sources, Coverage & Constraints Assessment

## 1. Overview of Data Sources

Cricsheet (`https://cricsheet.org`) is the authoritative source for freely available structured ball-by-ball cricket match data. Data is provided primarily in JSON and YAML formats alongside a People and Venue Register.

### Empirical Inspection Results (as of October 2026)

| Target Dataset | Cricsheet Endpoint | Format | Matches Available | Archive Size | Download Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Tests (Men)** | `/downloads/tests_male_json.zip` | JSON v1.3.0 | 897 matches | ~16.10 MB | Verified & Available |
| **Tier 1: ODIs (Men)** | `/downloads/odis_male_json.zip` | JSON v1.3.0 | 2,607 matches | ~16.86 MB | Verified & Available |
| **Tier 1: T20Is (Men)** | `/downloads/t20s_male_json.zip` | JSON v1.3.0 | 3,646 matches | ~13.88 MB | Verified & Available |
| **Tier 2: IPL (Men)** | `/downloads/ipl_male_json.zip` | JSON v1.3.0 | ~1,095 matches | ~4.95 MB | Verified & Available |
| **Tier 3: Syed Mushtaq Ali (Men)** | `/downloads/sma_male_json.zip` | JSON v1.3.0 | 695 matches | ~2.58 MB | Verified & Available |
| **People Register** | `/register/people.csv` | CSV | 18,683 people | ~1.6 MB | Verified & Available |
| **Names Register** | `/register/names.csv` | CSV | 27,500+ names | ~0.8 MB | Verified & Available |
| **Venues Register** | `/register/venues.csv` | CSV | ~1,200 venues | ~0.1 MB | Verified & Available |

*Note on Non-Official T20Is:* Cricsheet hosts a separate archive `/downloads/it20s_male_json.zip` (240 matches) for non-official international T20s. Official T20 Internationals reside in `t20s_male_json.zip`.

---

## 2. Coverage Gaps & Realities

### Senior Indian Domestic Cricket (Tier 3)
1. **Syed Mushtaq Ali Trophy (SMAT - T20)**:
   - **Status**: **Available** on Cricsheet (`sma_male_json.zip`, 695 matches).
   - Covers Indian domestic state associations (e.g., Mumbai, Karnataka, Tamil Nadu, Delhi, Saurashtra, Baroda).
2. **Ranji Trophy (First Class - Multi-Day)**:
   - **Status**: **NOT Available** as ball-by-ball structured data on Cricsheet.
   - Cricsheet's multi-day matches archive (`mdms_male_json.zip`) covers England County Championship, Australia Sheffield Shield, and New Zealand Plunket Shield, but **no** Ranji Trophy matches.
3. **Vijay Hazare Trophy (List A - One-Day)**:
   - **Status**: **NOT Available** as ball-by-ball structured data on Cricsheet.
   - Cricsheet's one-day matches archive (`odms_male_json.zip`) covers English and Australian domestic 50-over cups, but **no** Vijay Hazare Trophy matches.
4. **Other Indian Domestic Tournaments**:
   - Duleep Trophy, Deodhar Trophy, and Irani Cup are likewise unavailable on Cricsheet.

### Architectural Implication for Tier 3
- For Phase 1 ingestion, **Tier 3 senior domestic data will consist exclusively of the Syed Mushtaq Ali Trophy (SMAT)**.
- In accordance with our core principle (*"Correctness over superficial completeness / No fabricated data"*), we will **not** attempt to scrape unofficial third-party sites or synthesize fake Ranji / Hazare scorecards.
- The schema and pipeline will remain fully extensible so that if BCCI / First-Class scorecards become available later, they can be ingested into the exact same relational tables.

---

## 3. Metadata & Metric Limitations

Direct inspection of Cricsheet match JSONs and registry files reveals several metadata fields requested in the downstream architecture that are **not natively present** in raw Cricsheet data:

### A. Player Attributes in `dim_player_master`
- **Present in Cricsheet**:
  - `player_id` (Cricsheet 8-character hex hash, e.g. `252938a6` for Virat Kohli).
  - `full_name` / `name` / `unique_name`.
  - External registry keys: `key_cricinfo`, `key_bcci`, `key_cricbuzz`, `key_nvplay`, `key_pulse`.
- **Absent in Cricsheet**:
  - `dob` (Date of birth).
  - `batting_hand` (e.g., Right-hand bat, Left-hand bat).
  - `bowling_style` (e.g., Right-arm fast-medium, Slow left-arm orthodox).
  - `primary_role` / `taxonomic_subrole` (e.g., Opening batter, Middle-order anchor, Finisher, Wicketkeeper, All-rounder, Strike bowler).
- **Resolution Strategy**:
  - Store as explicit `NULL` / `'UNKNOWN'` during Step 3 raw ingestion.
  - During Step 5 (Cohort Extraction), apply a documented enrichment policy using the linked `key_cricinfo` to supplement missing roles and handedness for the target Indian cohort only.

### B. Event Metrics in `fact_ball_by_ball`
- **Present in Cricsheet**:
  - Innings, over, delivery index, batter, bowler, non-striker, batter runs, extras breakdown (wides, no-balls, byes, leg-byes, penalty), wicket flag, dismissal kind, dismissed player, fielders involved.
- **Absent in Cricsheet**:
  - `shot_control_flag` (requires Hawkeye/CricViz optical tracking).
  - `xRA` (Expected Runs Added — requires Phase 2 ML model).
  - `xW` (Expected Wickets — requires Phase 2 ML model).
  - `wpa_delta` (Win Probability Added — requires Phase 2 in-game win probability model).
  - `dismissed_player_rating` (requires Phase 2 Dynamic Rating Engine).
- **Resolution Strategy**:
  - Fields are explicitly created in the schema with `FLOAT` / `BOOLEAN` types, populated with `NULL`.
  - Formulas, feature definitions, and assumptions are formally documented before any derived values are computed.

### C. Environmental Context in `dim_match_context`
- **Present in Cricsheet**:
  - Match date, season, match type, venue name, city, toss winner, toss decision, match outcome (winner, win margins, eliminator/super-over flag), match officials.
- **Absent in Cricsheet**:
  - `pitch_surface_type` (e.g. red soil, black soil, hybrid turf).
  - `expected_turn_deg` (degrees of turn — requires optical tracking).
  - `boundary_length_sq`, `boundary_length_str` (exact square/straight boundary dimensions in meters).
- **Resolution Strategy**:
  - Populated with `NULL`. Venue-level aggregate baselines (e.g., average historical innings score at venue) will be calculated in Step 6 feature engineering.

### D. Pairwise Synergy Matrix
- `fact_pairwise_synergy_matrix`:
  - Relationships (left-right partnership synergy, bowling partnership pressure) require statistical inference across historical partnerships and bowling spells.
  - In Phase 1 Step 3, the table schema is formalized and registered in DuckDB; actual edge weights will be derived in Phase 2 / Stage 2 graph learning.

---

## 4. Cohort Achievability Assessment

The target cohort requirement is:
> **Active male Indian cricketers with qualifying senior-level match activity on or after 1 January 2020 (minimum 5 matches across Tiers 1–3).**

### Feasibility: **Fully Achievable**
1. **Tier 1**: All Indian men's international appearances (Tests, ODIs, T20Is) post-2020 are available.
2. **Tier 2**: All IPL matches post-2020 are available.
3. **Tier 3**: All Syed Mushtaq Ali Trophy matches post-2020 are available.
4. **Identification**:
   - Any player who represented team `"India"` is definitively an Indian international.
   - Any player who represented an Indian state association team in the Syed Mushtaq Ali Trophy without overseas player designation is definitively an Indian domestic player.
   - In the IPL, Indian domestic players can be distinguished from overseas players using the 4-overseas player per XI limit and nationality mappings.
5. **Sample Size**:
   - Over 500+ Indian male cricketers meet the $\ge 5$ match activity threshold across IPL + SMAT + Internationals since 2020-01-01.
