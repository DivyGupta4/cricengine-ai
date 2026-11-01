# CricEngine AI — Step 2 Completion Report

## 1. Step 2 Scope & Objectives
The objective of Step 2 was to acquire, cryptographically verify, and audit the approved Cricsheet match datasets and official registries without altering raw files or beginning canonical database ingestion.

### Approved Acquisition Scope:
- **Tier 1 (International Men)**: Tests (`tests_male_json.zip`), ODIs (`odis_male_json.zip`), T20Is (`t20s_male_json.zip`).
- **Tier 2 (Franchise Men)**: Indian Premier League (`ipl_male_json.zip`).
- **Tier 3 (Senior Domestic Men)**: Syed Mushtaq Ali Trophy (`sma_male_json.zip`).
- **Official Registries**: People (`people.csv`), Names (`names.csv`), Venues (`venues.csv`).

---

## 2. Acquisition & Integrity Verification Results

All five archives were downloaded atomically with temporary file swaps (`.part`), verified against zip corruption via `zf.testzip()`, and extracted safely preventing path traversal:

| Dataset | Archive Filename | SHA-256 Checksum | Size (MB) | Extracted Files | Match JSONs | Parse Success Rate |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Tests** | `tests_male_json.zip` | `cb8593cdad57b6de11f18dca778dd8776d0b3aab4eb5dfe3880a68a0e1e213cb` | 16.10 MB | 899 | 897 | 100.0% (0 errors) |
| **ODIs** | `odis_male_json.zip` | `8518aa42ff388c3f6fca06661bba839e8756680c3a35adbfa851f45364675224` | 16.86 MB | 2,609 | 2,607 | 100.0% (0 errors) |
| **T20Is** | `t20s_male_json.zip` | `691f1f42b86c93fbdbc53936ed69479f9306bf39c4c56b4c0729360051075c6d` | 13.88 MB | 3,648 | 3,646 | 100.0% (0 errors) |
| **IPL** | `ipl_male_json.zip` | `6fe9142db9e139e4f77a5634ddc61c1c72a26a56bee2fe5affe5921867de04b3` | 4.95 MB | 1,245 | 1,243 | 100.0% (0 errors) |
| **SMAT** | `sma_male_json.zip` | `14ebfdc1541d6211a8041249d5c8cc9b460fb729a27169959f0de68971444455` | 2.58 MB | 697 | 695 | 100.0% (0 errors) |
| **Total** | — | — | **54.37 MB** | **9,098** | **9,088** | **100.0% (9,088/9,088)** |

---

## 3. Detailed Investigation of IPL Match Count Discrepancy

- **Published Summary Count**: 1,095 matches
- **Actual Archive Match Files**: 1,243 matches (+148 matches)

### Season-by-Season Verification:
Inspection of match metadata across every season in `ipl_male` reveals the exact source of this discrepancy:
- Through Season 2023: 1,024 cumulative matches.
- Season 2024 (2024-03-22 to 2024-05-26): 71 matches $\to$ **Cumulative total: Exactly 1,095 matches**.
- Season 2025 (2025-03-22 to 2025-06-03): 74 matches $\to$ Cumulative total: 1,169 matches.
- Season 2026 (2026-03-28 to 2026-05-31): 74 matches $\to$ Cumulative total: **1,243 matches**.

**Root Cause**: The 1,095 figure published in static documentation reflects the total at the conclusion of the 2024 IPL season. The live archive includes the completed 2025 and 2026 seasons.

---

## 4. Manifest & Automated Testing Verification

1. **Manifest File**: Created at `data/raw_cricsheet/manifest.json`.
   - Records source URL, timestamp, archive path, full SHA-256, archive size, download status, extraction status, extracted count, and error fields.
   - Enhanced to support unchanged-archive detection and changed-archive historical backups.
2. **Automated Test Suite**:
   - `tests/test_acquisition.py`: 11 tests covering checksums, zip validation, safe extraction, path traversal blocking, manifest persistence, unreadable file detection, unchanged archive recognition, and changed archive backups.
   - `tests/test_environment.py`: 6 tests covering Python 3.12, DuckDB, Parquet, and configuration paths.
   - **Total Tests**: 17 passed in 1.38s with zero network dependencies.
