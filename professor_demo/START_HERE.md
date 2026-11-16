# CricEngine AI — Professor Demonstration Guide (`START_HERE.md`)

Welcome to the **CricEngine AI Demonstration Package**. This guide provides exact instructions to open, inspect, navigate, and present the production cricket data lake and lakehouse stores on your Mac without installing unnecessary software.

---

## Quick Start: 30-Second Demonstration Launch

Open Terminal on your Mac, navigate to the project directory, and run the automated walkthrough:

```bash
cd /Users/divygupta/Desktop/DL_DATABASE
.venv/bin/python professor_demo/run_demo_walkthrough.py
```

This interactive script guides you step-by-step through the 8 stages of the data lake architecture, executing live queries and displaying verified dataframes with one press of the `[ENTER]` key per step.

---

## 1. What Applications to Use on Your Mac

You **do not** need to install any new software. Your Mac environment already contains everything required:

1. **For Database & Parquet Datasets (Recommended): Python 3.12 Virtual Environment (`.venv`)**
   - **Path:** `/Users/divygupta/Desktop/DL_DATABASE/.venv/bin/python`
   - **Pre-installed Packages:** `duckdb` (v2.0.0), `pyarrow` (v26.0.0), `pandas` (v3.1.0).
   - **Why:** DuckDB natively executes lightning-fast SQL over both relational tables (`cricengine.duckdb`) and partitioned Parquet datasets (`read_parquet(...)`) without requiring any database server or daemon.

2. **For Raw JSON Match Files:**
   - **Terminal:** `cat`, `less`, or `python -m json.tool`
   - **Web Browser (GUI):** Google Chrome, Brave, or Safari (`open -a "Google Chrome" <path-to-json>`).

3. **Optional GUI (Only if you or the professor prefer a standalone graphical UI):**
   - **Tad (Parquet Viewer):** `brew install --cask tad` (lightweight, zero-config GUI for `.parquet` files).
   - **DBeaver Community / TablePlus:** GUI for DuckDB database files via the DuckDB JDBC driver.
   *Note: These GUIs are strictly optional; the provided Python CLI tools require zero installation.*

---

## 2. Dataset Directory Map

The data lake is structured into six clean tiers:

```
DL_DATABASE/
├── data/
│   ├── raw_cricsheet/                  <-- 1. RAW INGESTION LAYER
│   │   ├── archives/                   (5 original ZIP archives from Cricsheet)
│   │   ├── extracted/                  (9,108 extracted match JSON files)
│   │   │   ├── odis_male/              (2,611 files)
│   │   │   ├── t20s_male/              (3,650 files)
│   │   │   ├── tests_male/             (901 files)
│   │   │   ├── ipl_male/               (1,247 files)
│   │   │   └── sma_male/               (699 files)
│   │   └── manifest.json               (Download timestamps, SHA-256 hashes)
│   │
│   └── datalake/
│       ├── curated/                    <-- 2. CANONICAL DUCKDB DATABASE
│       │   └── cricengine.duckdb       (383 MB, 14 3NF tables, 4.9M rows)
│       │
│       ├── enrichment_v3b/             <-- 3. ENRICHMENT & METADATA LAYER
│       │   ├── dim_player_master_enriched.parquet  (7,014 players with hand/role)
│       │   ├── fact_match_participation_v3b.parquet(200,709 verified appearances)
│       │   └── historical_roster_classifications.parquet (86,224 role tags)
│       │
│       ├── feature_store_v3b/          <-- 4. FEATURE STORE (1,164 PARQUET FILES)
│       │   ├── player_match/           (200,709 single-match metric rows)
│       │   ├── rolling_match/          (602,127 rows: 5, 10, 20-match form)
│       │   ├── rolling_time/           (602,127 rows: 30, 90, 365-day form)
│       │   ├── contextual_features/    (200,709 rows: park factors, opp quality)
│       │   └── contextual_baselines/   (Venue and phase baseline reference tables)
│       │
│       ├── rating_store_v4/            <-- 5. LATENT RATING STORE (145 FILES)
│       │   ├── pre_match_snapshots/    (19,642 pre-match D-1 rating snapshots)
│       │   ├── player_rating_current/  (9,406 active ratings across formats)
│       │   └── player_rating_history/  (73,039 rating progression checkpoints)
│       │
│       └── predictive_store_v4c/       <-- 6. PREDICTIVE STORE (86 FILES)
│           ├── player_match_vorp/      (9,708 rows: Value Over Replacement Player)
│           ├── batting_predictions/    (9,708 rows: forecasted runs & intervals)
│           ├── bowling_predictions/    (9,708 rows: forecasted overs, wickets)
│           ├── fielding_predictions/   (9,708 rows: expected catches, runouts)
│           └── evaluation_metrics/     (Calibration & benchmark comparisons)
│
└── professor_demo/                     <-- DEMONSTRATION TOOLS & SCRIPTS
    ├── START_HERE.md                   (This guide)
    ├── run_demo_walkthrough.py         (Automated 8-stage professor presentation)
    ├── explore_database.py             (Interactive DuckDB explorer & SQL runner)
    ├── explore_features.py             (Interactive Parquet feature store inspector)
    ├── sample_queries.sql              (9 verified production SQL queries)
    └── dataset_inventory.md            (Technical inventory of all tables/stores)
```

---

## 3. How to Inspect Tables and Sample Records

### Option A: Use the Interactive Database Explorer (`explore_database.py`)
Run the tool interactively:
```bash
.venv/bin/python professor_demo/explore_database.py
```
Or run directly with CLI command flags:
```bash
# 1. List all 14 tables with exact row counts
.venv/bin/python professor_demo/explore_database.py --list

# 2. View schema for any table (e.g., fact_ball_by_ball or dim_match)
.venv/bin/python professor_demo/explore_database.py --schema fact_ball_by_ball

# 3. View sample records from a table
.venv/bin/python professor_demo/explore_database.py --sample dim_match --limit 5

# 4. Run pre-built example queries
.venv/bin/python professor_demo/explore_database.py --example 1
```

### Option B: Use the Interactive Feature Store Explorer (`explore_features.py`)
```bash
# 1. List all Parquet datasets across the lakehouse
.venv/bin/python professor_demo/explore_features.py --list

# 2. Inspect schema and description of a specific dataset
.venv/bin/python professor_demo/explore_features.py --summary fs_player_match

# 3. View sample records from a Parquet dataset
.venv/bin/python professor_demo/explore_features.py --sample ps_vorp --limit 5

# 4. View end-to-end features for demonstration match 1389392
.venv/bin/python professor_demo/explore_features.py --demo-match
```

### Option C: Run Custom SQL from the Terminal (One-Liner)
DuckDB allows one-line read-only querying directly from Python:
```bash
.venv/bin/python -c "
import duckdb
conn = duckdb.connect('data/datalake/curated/cricengine.duckdb', read_only=True)
print(conn.execute('SELECT match_id, team_1, team_2, start_date FROM dim_match LIMIT 5').df())
conn.close()
"
```

---

## 4. Understanding Data Lineage Across Stores

To explain the project to your professor, highlight the **five-stage analytical lifecycle**:

1. **Raw Ingestion Layer:**
   Primary Cricsheet JSON files contain nested trees (`info`, `teams`, `innings`, `overs`, `deliveries`). While rich, raw JSON is unstructured, duplicated across matches, and impossible to query efficiently at scale.

2. **Canonical Relational Core (`cricengine.duckdb`):**
   The raw files are parsed and normalized into a clean **Third Normal Form (3NF)** relational model with 14 tables. Entities like players (`dim_player_master`), matches (`dim_match`), innings (`fact_innings`), and ball-by-ball deliveries (`fact_ball_by_ball`) have strict primary and foreign keys, enabling microsecond relational filtering.

3. **Enrichment & Identity Resolution (`enrichment_v3b`):**
   Raw player strings from multiple leagues are disambiguated through canonical registry mappings (`dim_player_master_enriched`), assigning stable player IDs, playing roles, and historical batting/bowling classifications.

4. **Engineered Feature Store (`feature_store_v3b`):**
   Event data is aggregated into partitioned Parquet files:
   - `player_match`: 49 transformed single-match statistics (batting strike rate, bowling load, fielding involvements).
   - `rolling_match`: Multi-scale moving windows (5, 10, 20 matches) with exponential decay and empirical Bayes shrinkage.
   - `rolling_time`: Calendar-day windows (30, 90, 365 days).
   - `contextual_features`: Venue park factors and opposition strength indices.

5. **Bayesian Rating Store (`rating_store_v4`) & Predictive VORP (`predictive_store_v4c`):**
   - Prior to match start, player latent skill ratings ($\theta$, rating $r$, epistemic uncertainty $rd$) are snapshotted in `pre_match_snapshots` (**D-1 guarantee** ensuring 0% lookahead data leakage).
   - Post-match, actual outputs are compared against replacement-level expectations to produce **Value Over Replacement Player (VORP)** metrics in `player_match_vorp`.

---

## 5. Recommended 5–10 Minute Professor Demonstration Walkthrough

Follow this scripted presentation when sharing your screen:

### **[Minute 0–2] Introduction & Raw Ingestion**
- **Action:** Open Terminal and show an original raw JSON file.
  ```bash
  cat data/raw_cricsheet/extracted/t20s_male/1389392.json | head -n 35
  ```
- **Talking Point:** *"Professor, we ingested 9,108 raw match files from Cricsheet across Tests, ODIs, T20Is, IPL, and domestic leagues. Here is match 1389392 (India vs Australia T20I). As you can see, the data starts as deeply nested, unindexed JSON."*

### **[Minute 2–4] The Relational Lakehouse Core (DuckDB)**
- **Action:** Show the 14 relational tables in DuckDB.
  ```bash
  .venv/bin/python professor_demo/explore_database.py --list
  ```
- **Action:** Run a query displaying the ball-by-ball deliveries of the first over.
  ```bash
  .venv/bin/python professor_demo/explore_database.py --example 2
  ```
- **Talking Point:** *"We parsed the raw JSON into an in-process, columnar DuckDB database containing 14 relational tables and over 4.9 million rows. Fact and dimension tables separate match context, innings, deliveries, and dismissals with complete relational integrity."*

### **[Minute 4–6] Dismissals, Player Participation & Roster Reconciliation**
- **Action:** Show dismissal events with bowler and fielder attribution.
  ```bash
  .venv/bin/python professor_demo/explore_database.py --example 4
  ```
- **Talking Point:** *"Notice how complex cricket events are resolved: a caught dismissal accurately links both the credited bowler and the capturing fielder, handling substitute fielders without referential failure."*

### **[Minute 6–8] Feature Engineering & Moving Windows**
- **Action:** Inspect the Parquet Feature Store.
  ```bash
  .venv/bin/python professor_demo/explore_features.py --list
  ```
- **Action:** Show rolling match features for Suryakumar Yadav and Glenn Maxwell.
  ```bash
  .venv/bin/python professor_demo/explore_database.py --example 6
  ```
- **Talking Point:** *"Our Feature Store v3b stores 1,164 partitioned Parquet files. Here we see multi-scale rolling windows (5, 10, and 20 matches). Notice how exponential decay and shrinkage capture player form while eliminating lookahead bias."*

### **[Minute 8–10] Pre-Match Bayesian Ratings & VORP Predictions**
- **Action:** Run the full end-to-end lineage join.
  ```bash
  .venv/bin/python -c "
  import resource; resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))
  import duckdb
  conn = duckdb.connect('data/datalake/curated/cricengine.duckdb', read_only=True)
  with open('professor_demo/sample_queries.sql') as f:
      q = f.read().split('QUERY 9:')[1].split(';')[0].replace('--', '')
  print(conn.execute(q).df().to_string(index=False))
  conn.close()
  "
  ```
- **Talking Point:** *"In this single query, we join our relational dimension master, the Feature Store, pre-match Bayesian rating snapshots (D-1), and our predictive VORP model. We can see Ravi Bishnoi's pre-match bowling rating of 1,647.9 translating into a match VORP of +11.45 runs after taking 3 wickets."*

---

## 6. Verification and Non-Negotiable Safety Guarantees

- **Database Integrity:** The canonical database `cricengine.duckdb` is opened strictly with `read_only=True`. Its SHA-256 hash (`a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae`) is continuously verified.
- **Mac OS File Descriptors:** macOS has a default limit of 256 open file descriptors (`ulimit -n`). All demo scripts automatically increase this limit to 4,096 at startup, ensuring smooth multi-file Parquet partition scanning without errors.
- **Zero Data Modification:** No production source code, checksum manifests, or feature store partitions are regenerated or modified during the demonstration.
