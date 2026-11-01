# CricEngine AI — Source Data Inventory & Verification Audit

> **Generated at**: `2026-10-29 21:08:25 UTC`  
> **Audit Status**: **100% Verified** on physical local archives. All match JSON files parsed with zero unreadable or corrupt records.

---

## 1. Summary of Acquired Match Datasets

| Competition | Format | Tier | Archive Filename | Size (MB) | Reported Count | Actual Readable Matches | Distinct Match IDs | Unreadable | Earliest Date | Latest Date |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Test Matches** | Test | Tier 1 | `tests_male_json.zip` | 16.10 MB | 897 | **897** | 897 | 0 | 2001-12-19 | 2026-10-22 |
| **One-Day Internationals** | ODI | Tier 1 | `odis_male_json.zip` | 16.86 MB | 2,607 | **2,607** | 2,607 | 0 | 2002-06-27 | 2026-10-25 |
| **T20 Internationals** | T20I | Tier 1 | `t20s_male_json.zip` | 13.88 MB | 3,646 | **3,646** | 3,646 | 0 | 2005-02-17 | 2026-10-25 |
| **Indian Premier League** | T20 | Tier 2 | `ipl_male_json.zip` | 4.95 MB | 1,095 | **1,243** | 1,243 | 0 | 2008-04-18 | 2026-05-31 |
| **Syed Mushtaq Ali Trophy** | T20 | Tier 3 | `sma_male_json.zip` | 2.58 MB | 695 | **695** | 695 | 0 | 2016-01-02 | 2024-12-15 |

**Totals Across All 5 Competitions**:
- **Total Match Archives**: 5 ZIP files
- **Total Match JSON Files**: **9,088**
- **Successfully Readable Files**: **9,088 (100.0%)**
- **Unreadable / Corrupt Files**: **0 (0.0%)**

---

## 2. Dataset Cryptographic Provenance & Manifest

| Dataset Key | Source URL | Retrieval Timestamp (UTC) | Archive SHA-256 Checksum | Extraction Status |
| :--- | :--- | :--- | :--- | :---: |
| `tests_male` | [https://cricsheet.org/downloads/tests_male_json.zip](https://cricsheet.org/downloads/tests_male_json.zip) | `2026-10-29T21:04:41.905986+00:00` | `cb8593cdad57b6de11f18dca778dd8776d0b3aab4eb5dfe3880a68a0e1e213cb` | SUCCESS |
| `odis_male` | [https://cricsheet.org/downloads/odis_male_json.zip](https://cricsheet.org/downloads/odis_male_json.zip) | `2026-10-29T21:04:53.363185+00:00` | `8518aa42ff388c3f6fca06661bba839e8756680c3a35adbfa851f45364675224` | SUCCESS |
| `t20s_male` | [https://cricsheet.org/downloads/t20s_male_json.zip](https://cricsheet.org/downloads/t20s_male_json.zip) | `2026-10-29T21:05:01.790670+00:00` | `691f1f42b86c93fbdbc53936ed69479f9306bf39c4c56b4c0729360051075c6d` | SUCCESS |
| `ipl_male` | [https://cricsheet.org/downloads/ipl_male_json.zip](https://cricsheet.org/downloads/ipl_male_json.zip) | `2026-10-29T21:05:05.772062+00:00` | `6fe9142db9e139e4f77a5634ddc61c1c72a26a56bee2fe5affe5921867de04b3` | SUCCESS |
| `sma_male` | [https://cricsheet.org/downloads/sma_male_json.zip](https://cricsheet.org/downloads/sma_male_json.zip) | `2026-10-29T21:05:10.280803+00:00` | `14ebfdc1541d6211a8041249d5c8cc9b460fb729a27169959f0de68971444455` | SUCCESS |

---

## 3. Discrepancy Analysis: Reported vs. Actual Match Counts

The project instructions require explicit distinction between counts reported on Cricsheet's webpage and counts actually present inside downloaded archives:

| Competition | Cricsheet Webpage Count | Downloaded Archive File Count | Discrepancy | Investigation & Root Cause |
| :--- | :---: | :---: | :---: | :--- |
| **Test Matches** | 897 | 897 | **0** | Exact match between published catalogue and archive contents. |
| **One-Day Internationals** | 2,607 | 2,607 | **0** | Exact match between published catalogue and archive contents. |
| **T20 Internationals** | 3,646 | 3,646 | **0** | Exact match between published catalogue and archive contents. |
| **Indian Premier League** | 1,095 | 1,243 | **+148** | Archive contains 1,243 matches vs published 1,095 (+148). Cricsheet's static summary text reflects earlier season counts, whereas the actual archive includes completed matches through May 2026. |
| **Syed Mushtaq Ali Trophy** | 695 | 695 | **0** | Exact match between published catalogue and archive contents. |

---

## 4. Official Registry Inspection

Cricsheet identity and venue registries downloaded from `https://cricsheet.org/register/`:

| Registry | Filename | Size (KB) | Row Count | SHA-256 Checksum | Available Columns |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **People** | `people.csv` | 1158.7 KB | **18,683** | `ffacf43c141d729f...` | `identifier`, `name`, `unique_name`, `key_bcci`, `key_bcci_2` (+17 more) |
| **Names** | `names.csv` | 158.7 KB | **7,551** | `cde5292c15be1cf0...` | `identifier`, `name` |
| **Venues** | `venues.csv` | 20.8 KB | **272** | `a80150a14b90d615...` | `identifier`, `name`, `unique_name`, `key_cricinfo`, `key_cricinfo_2` |

### Registry Key Findings:
- **`people.csv` (18,683 rows)**: Maps Cricsheet hex identifiers (e.g. `252938a6`) to external database IDs.
  - **18,638 players (99.76%)** have an official ESPN Cricinfo ID (`key_cricinfo`).
  - **1,321 Indian players** have a BCCI registry ID (`key_bcci`).
  - **50 players** have a Cricbuzz ID (`key_cricbuzz`).
  - **Crucial Schema Reality**: Does **not** contain date-of-birth, batting hand, bowling style, or playing role.
- **`names.csv` (7,551 rows)**: Maps 5,583 unique Cricsheet identifiers to alternative alias names (1,818 players possess multiple documented aliases).
- **`venues.csv` (272 rows)**: Maps official venue names and unique names to ESPN Cricinfo venue keys.
- **Cross-Reference Integrity**: In a validation sample across 1,000 match files and 26,110 player references, **100.0% of player identifiers resolved cleanly to `people.csv`**.

---

## 5. Match JSON Schema & Format Inspection

Inspection of representative match files across all 5 datasets revealed the following schema realities:

### A. Schema Versions Observed
- `1.2.0`: Standard format across all SMAT matches, IPL matches, and older internationals.
- `1.3.0`: Enhanced format in recent internationals (2024–2026), adding `actual_delivery` (e.g., `"0.1"`), `balls_per_over` (`6`), and `match_type_number`.

### B. Event & Delivery Structure
- **Deliveries**: Grouped inside overs: `innings[i].overs[j].deliveries[k]`.
- **Player Identifiers**: Player names in deliveries (e.g. `"batter": "V Kohli"`) map to Cricsheet hex IDs via `info.registry.people`.
- **Runs**: Structured dictionary with `"batter"`, `"extras"`, and `"total"`.
- **Extras**: Breakdown dictionary with keys: `"wides"`, `"noballs"`, `"byes"`, `"legbyes"`, `"penalty"`.
- **Wickets**: List of wicket events with `"kind"`, `"player_out"`, and `"fielders"`.
- **Replacements / Impact Players**: Found in modern IPL matches (`info.innings[i].overs[j].deliveries[k].replacements.match[0]`) containing `{"in": "...", "out": "...", "reason": "impact_player"}`.
- **Super Overs**: Recorded as distinct innings elements with `"super_over": true`.

---

## 6. Known Source Limitations & Architectural Implications

1. **Absence of Ranji Trophy and Vijay Hazare Trophy**:
   - Cricsheet does not publish ball-by-ball structured data for Indian First-Class (Ranji) or List-A (Vijay Hazare) competitions.
   - Tier 3 domestic data is bounded to the **Syed Mushtaq Ali Trophy (T20 format, 695 matches)**.
   - No fake records will be synthesized. The relational model will support them seamlessly if alternative First-Class data is integrated in later phases.
2. **Unobserved Delivery-Level Metrics**:
   - Shot control (`shot_control_flag`), expected runs added (`xRA`), expected wickets (`xW`), win probability added (`wpa_delta`), and dismissed player rating do not exist in Cricsheet raw JSON.
   - These fields will remain strictly unpopulated or modeled in Phase 2.
3. **Environmental Context Limitations**:
   - Pitch surface type, degrees of turn, and boundary lengths (meters) are not provided by Cricsheet.
   - They will be preserved as explicit `NULL` in `dim_match_context` without guessing.