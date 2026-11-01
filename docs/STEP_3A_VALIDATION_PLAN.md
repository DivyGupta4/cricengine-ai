# CricEngine AI — Step 3A Data Validation & Invariant Plan (Revised)

> **Plan Stage**: Step 3A Pre-Ingestion Quality Specification  
> **Target Execution**: Embedded in parser (`etl/parse_cricsheet.py`) and regression test suite (`tests/test_parser_schema.py`)  
> **Status**: Approved for Step 3B Execution

---

## 1. Quality Framework & Severity Levels

Validation invariants are divided into two operational tiers:

| Severity Level | Definition | Ingestion Action | Example |
| :--- | :--- | :--- | :--- |
| **`CRITICAL`** | Severe corruption, structural failure, or broken entity integrity. | Ingestion of the match is **halted/rejected**; record quarantined; logged to `data_quality_results`. | Unparseable JSON, duplicate match ID, delivery math imbalance, broken foreign key. |
| **`WARNING`** | Source anomaly, historical scorecard discrepancy, or missing optional context. | Match is **admitted** with an audit flag recorded in `data_quality_results`. | Missing host city, rain abandonment, umpire miscounted over (5 or 7 balls), minor historical run difference. |

---

## 2. Invariant Matrix & Documented Rejection Rationales

### A. Match & Context Integrity

| Rule ID | Severity | Invariant Statement | Documented Rejection Rationale |
| :--- | :---: | :--- | :--- |
| **`M1`** | **CRITICAL** | `match_id` must be globally unique across all archives. | Duplicate match IDs violate relational primary keys and would overwrite or cross-contaminate ball-by-ball events across disparate matches. |
| **`M2`** | **CRITICAL** | Match dates array must contain at least 1 valid ISO 8601 date, and `start_date <= end_date`. | Chronological temporal ordering is essential for Elo/Glicko-2 ratings and career trajectory feature generation. Invalid dates corrupt temporal state. |
| **`M3`** | **CRITICAL** | Exactly 2 distinct competing teams named in `dim_match`. | Cricket is inherently a bilateral contest; matches with fewer or greater than 2 teams indicate broken JSON structure. |
| **`M4.1`** | **CRITICAL** | `venue_name` must be non-null, non-empty string. | Missing venue prevents ground identification and spatial context modeling; matches lacking ground name are rejected. |
| **`M4.2`** | **WARNING** | Host `city` is optional; if missing, preserved as SQL NULL. | Non-fatal: ~12.7% of historical venues lack city in Cricsheet. Never fabricate city names from venue strings. Admitted with audit log. |
| **`M5`** | **WARNING** | In tied or abandoned matches, verify outcome integrity (`'tie'`, `'no result'`). | Non-fatal: Tied matches (with Super Overs) or abandoned matches without winner are legitimate cricket occurrences. |

### B. Innings Reconciliation & Sequence

| Rule ID | Severity | Invariant Statement | Documented Rejection Rationale |
| :--- | :---: | :--- | :--- |
| **`I1`** | **CRITICAL** | `innings_num` must be sequential integers starting from 1 without gaps ($1, 2, \dots$). | Missing innings numbers corrupt match state transitions and chase-pressure calculations in win-probability models. |
| **`I2`** | **CRITICAL** | Mathematical Delivery Run Balance: $\sum \text{runs\_total} \equiv \sum \text{runs\_batter} + \sum \text{runs\_extras}$. | Internal arithmetic inconsistency indicates corrupted ball events that destroy batter strike-rates and bowler economy stats. |
| **`I3`** | **CRITICAL** | Scorecard Run Discrepancy without rain adjustment must not exceed 5 runs ($\|\text{reconciled} - \text{declared}\| \le 5$). | Discrepancies $> 5$ runs indicate missing overs, misattributed boundaries, or truncated records that distort player performance metrics. |
| **`I4`** | **WARNING** | Minor historical discrepancy ($\le 5$ runs) or DLS revised targets. | Admitted with audit flag: early 2000s scorecards occasionally had minor clerical differences between official scorers and newspaper records. |

### C. Delivery Event Arithmetic & Semantics

| Rule ID | Severity | Invariant Statement | Documented Rejection Rationale |
| :--- | :---: | :--- | :--- |
| **`D1`** | **CRITICAL** | Extras component balance: $\text{runs\_extras} = \text{wides} + \text{noballs} + \text{byes} + \text{legbyes} + \text{penalty}$. | Extras must equal the sum of their constituent types to ensure correct bowling economy and team concession statistics. |
| **`D2`** | **CRITICAL** | Legal Delivery Invariant: $\text{is\_legal\_delivery} \iff (\text{wides} = 0 \land \text{noballs} = 0)$. | Bowling workloads, legal balls bowled, and over completions directly depend on this definition. Errors distort bowler workloads. |
| **`D3`** | **CRITICAL** | Monotonic Delivery Sequence: `delivery_num` starts at 1 and increments by 1 on every delivery attempt within the over. | Non-monotonic delivery keys break ball-by-ball ordering and replay simulations. |
| **`D4`** | **WARNING** | Irregular over lengths (fewer than 6 legal balls due to rain, or 5/7 balls due to umpire counting error). | Non-fatal: Real umpires occasionally miscount balls (e.g. 5 or 7 balls in an over); these must be preserved as authentic historical events. |

### D. Dismissal & Fielder Integrity

| Rule ID | Severity | Invariant Statement | Documented Rejection Rationale |
| :--- | :---: | :--- | :--- |
| **`W1`** | **CRITICAL** | Every dismissed player must match the active striker or non-striker on that ball. | Prevents ghost dismissals of players not on the field, which would corrupt player survival curves and wicket hazard models. |
| **`W2`** | **CRITICAL** | Multi-wicket deliveries must generate distinct child records with unique `dismissal_id`. | Single-record compression drops secondary dismissals (e.g. timed out during a caught delivery), losing critical match events. |
| **`W3`** | **WARNING** | Fielder IDs may be null if the fielder was an unlisted substitute. | Non-fatal: Substitute fielders often lack registry profiles in Cricsheet; recorded as `is_substitute = True` without rejecting the match. |

### E. Player Identity & Participation Integrity

| Rule ID | Severity | Invariant Statement | Documented Rejection Rationale |
| :--- | :---: | :--- | :--- |
| **`P1`** | **CRITICAL** | Canonical Player IDs must resolve to non-colliding entities; zero name-only merging. | Merging different players with the same name (e.g. two players named 'A Khan') corrupts career longitudinal modeling. |
| **`P2`** | **CRITICAL** | Officials (umpires, referees) must NOT be inserted into `dim_player_master` unless they actively played as a player. | Contaminating player registries with non-playing officials destroys data hygiene and model feature spaces. |
| **`P3`** | **WARNING** | Nominated squad members with zero on-field events are tagged as `UNCONFIRMED_ROSTER`. | Non-fatal: Captures modern squad announcements (e.g. 12-15 player sheets) without misrepresenting non-participating players as starters. |

---

## 3. Triage & Quarantine Policy for Rejected Files

When a file triggers a `CRITICAL` violation:
1. **Quarantine**: The file is skipped from production tables and staged into `data/quarantine/<competition>/<match_id>.json`.
2. **Audit Logging**: A structured entry is written to `data_quality_results` containing:
   - `check_id`
   - `execution_timestamp`
   - `match_id`
   - `table_name`
   - `rule_name`
   - `severity = 'CRITICAL'`
   - `status = 'FAIL'`
   - `failure_details` (exact numeric delta or key collision details)
3. **Investigation Workflow**: Data engineering investigates quarantined matches. If an upstream bug in Cricsheet is confirmed, an explicit override rule with cryptographic lineage must be documented in `docs/DATA_OVERRIDES.md` before admission.
