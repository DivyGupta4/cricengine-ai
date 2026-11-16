#!/usr/bin/env python3
"""
explore_features.py — Parquet Lakehouse & Feature Store Explorer for CricEngine AI.

Designed for professor demonstration.
Inspects Feature Store (v3b), Rating Store (v4), Predictive Store (v4c), and Enrichment layers.
Strictly read-only access.
"""

import os
import sys
import glob
import argparse

# Ensure soft limit on open file descriptors is increased on macOS
try:
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 4096:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
except Exception:
    pass

try:
    import duckdb
    import pyarrow.parquet as pq
except ImportError:
    print("[ERROR] Required packages (duckdb, pyarrow) missing.")
    print("Please run this script using the project virtual environment:")
    print("    .venv/bin/python professor_demo/explore_features.py")
    sys.exit(1)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DATALAKE_DIR = os.path.join(PROJECT_ROOT, "data", "datalake")


DATASET_CATALOG = {
    # 1. Feature Store v3b
    "fs_player_match": {
        "store": "Feature Store v3b",
        "name": "Player Match Features",
        "path": os.path.join(DATALAKE_DIR, "feature_store_v3b", "player_match", "**", "*.parquet"),
        "hive": True,
        "purpose": "Match-level transformed player performances (runs, balls, strike rate, wickets, bowling load, fielding involvements). Serves as base input for rolling features and rating calculations.",
        "sample_columns": ["player_id", "match_id", "team_name", "opposition_team", "runs_scored", "balls_faced", "strike_rate", "overs_bowled", "wickets_credited", "economy_rate", "match_format", "season"]
    },
    "fs_rolling_match": {
        "store": "Feature Store v3b",
        "name": "Rolling Match Windows (Form)",
        "path": os.path.join(DATALAKE_DIR, "feature_store_v3b", "rolling_match", "**", "*.parquet"),
        "hive": True,
        "purpose": "Rolling window metrics over 5, 10, and 20 recent matches. Captures player form, exponential decay rates, and bayesian empirical shrinkage while strictly avoiding data leakage.",
        "sample_columns": ["player_id", "match_id", "evaluation_date", "matches_in_window", "rolling_runs_scored", "rolling_batting_avg", "rolling_batting_sr", "rolling_wickets_taken", "window_size", "match_format"]
    },
    "fs_rolling_time": {
        "store": "Feature Store v3b",
        "name": "Rolling Time Windows (Recency)",
        "path": os.path.join(DATALAKE_DIR, "feature_store_v3b", "rolling_time", "**", "*.parquet"),
        "hive": True,
        "purpose": "Time-based rolling windows over 30, 90, and 365 calendar days. Tracks player performance velocity over time independent of match frequency.",
        "sample_columns": ["player_id", "match_id", "evaluation_date", "matches_in_window", "rolling_runs_scored", "rolling_batting_avg", "rolling_wickets_taken", "window_days", "match_format"]
    },
    "fs_contextual": {
        "store": "Feature Store v3b",
        "name": "Contextual Features & Baselines",
        "path": os.path.join(DATALAKE_DIR, "feature_store_v3b", "contextual_features", "**", "*.parquet"),
        "hive": True,
        "purpose": "Environmental and contextual adjustments: historical venue park factors, opponent bowling quality index, opponent batting strength, home/away advantage.",
        "sample_columns": ["player_id", "match_id", "canonical_venue_name", "venue_historical_park_factor", "opposition_bowling_quality_index", "opposition_batting_quality_index", "is_home_match"]
    },

    # 2. Player Rating Store v4
    "rs_pre_match": {
        "store": "Rating Store v4",
        "name": "Pre-Match Rating Snapshots",
        "path": os.path.join(DATALAKE_DIR, "rating_store_v4", "pre_match_snapshots", "**", "*.parquet"),
        "hive": True,
        "purpose": "Point-in-time latent player skill ratings evaluated strictly prior to match start (D-1 guarantee). Prevents lookahead leakage for predictive modelling.",
        "sample_columns": ["player_id", "match_id", "match_date", "inferred_role", "pre_r_bat", "pre_rd_bat", "pre_r_bowl", "pre_rd_bowl", "pre_vorp"]
    },
    "rs_current": {
        "store": "Rating Store v4",
        "name": "Current Player Ratings (Latent Ability)",
        "path": os.path.join(DATALAKE_DIR, "rating_store_v4", "player_rating_current", "**", "*.parquet"),
        "hive": True,
        "purpose": "Latest latent skill parameters (theta, variance, Glicko-style rating r and deviation rd) across batting, bowling, fielding, and all-round composite roles.",
        "sample_columns": ["player_id", "as_of_date", "inferred_role", "r_bat", "rd_bat", "r_bowl", "rd_bowl", "r_allround", "vorp_rating", "rating_status"]
    },
    "rs_history": {
        "store": "Rating Store v4",
        "name": "Player Rating History (Checkpoints)",
        "path": os.path.join(DATALAKE_DIR, "rating_store_v4", "player_rating_history", "**", "*.parquet"),
        "hive": True,
        "purpose": "Time-series career trajectories of player rating evolutions, tracking uncertainty decay as exposure increases.",
        "sample_columns": ["player_id", "as_of_date", "observations_count", "effective_exposure_bat", "r_bat", "rd_bat", "r_bowl", "rd_bowl", "vorp_rating"]
    },

    # 3. Predictive Store v4c
    "ps_vorp": {
        "store": "Predictive Store v4c",
        "name": "Player Match VORP (Value Over Replacement)",
        "path": os.path.join(DATALAKE_DIR, "predictive_store_v4c", "player_match_vorp", "**", "*.parquet"),
        "hive": True,
        "purpose": "Evaluates each player's marginal contribution in runs/wickets over a theoretical replacement-level player for that specific match context and role.",
        "sample_columns": ["player_id", "match_id", "match_date", "inferred_role", "vorp_bat", "vorp_bowl", "vorp_field", "vorp_total", "is_above_replacement"]
    },
    "ps_batting": {
        "store": "Predictive Store v4c",
        "name": "Batting Predictions & Intervals",
        "path": os.path.join(DATALAKE_DIR, "predictive_store_v4c", "batting_predictions", "**", "*.parquet"),
        "hive": True,
        "purpose": "Probabilistic forecasts of runs scored, boundary rate, and dismissal probabilities along with 50%, 80%, 90%, and 95% calibrated confidence intervals.",
        "sample_columns": ["player_id", "match_id", "match_date", "inferred_role", "expected_runs", "runs_interval_50_low", "runs_interval_50_high", "runs_interval_90_low", "runs_interval_90_high", "actual_runs_scored"]
    },
    "ps_bowling": {
        "store": "Predictive Store v4c",
        "name": "Bowling Predictions & Intervals",
        "path": os.path.join(DATALAKE_DIR, "predictive_store_v4c", "bowling_predictions", "**", "*.parquet"),
        "hive": True,
        "purpose": "Probabilistic forecasts of overs, wickets, and runs conceded with hazard rate modeling and empirical confidence intervals.",
        "sample_columns": ["player_id", "match_id", "match_date", "inferred_role", "expected_overs_bowled", "expected_wickets", "expected_runs_conceded", "actual_wickets_taken", "actual_runs_conceded"]
    },

    # 4. Enrichment Layer v3b
    "en_rosters": {
        "store": "Enrichment Layer v3b",
        "name": "Historical Roster Classifications",
        "path": os.path.join(DATALAKE_DIR, "enrichment_v3b", "historical_roster_classifications.parquet"),
        "hive": False,
        "purpose": "Archetype role classifications (Opener, Middle Order, Pace Specialist, Spinner, etc.) derived from career participation and performance profiles.",
        "sample_columns": ["player_id", "inferred_role", "role_confidence", "is_pure_batter", "is_pure_bowler", "is_allrounder"]
    }
}


def list_datasets(conn):
    """List all available Parquet datasets with metadata."""
    print("\n" + "=" * 80)
    print("  CRICENGINE AI: PARQUET LAKEHOUSE DATASET CATALOG")
    print("=" * 80)
    print(f" {'Key':<16} | {'Layer / Store':<20} | {'Dataset Name':<30} | {'Files':>6}")
    print("-" * 80)
    for key, meta in DATASET_CATALOG.items():
        files = glob.glob(meta["path"], recursive=True)
        file_count = len(files)
        print(f" {key:<16} | {meta['store']:<20} | {meta['name']:<30} | {file_count:>6}")
    print("=" * 80 + "\n")


def show_dataset_summary(conn, key):
    """Show detailed schema, row count, and purpose for a dataset."""
    if key not in DATASET_CATALOG:
        print(f"[ERROR] Unknown dataset key '{key}'. Available keys: {list(DATASET_CATALOG.keys())}")
        return

    meta = DATASET_CATALOG[key]
    files = glob.glob(meta["path"], recursive=True)
    if not files:
        print(f"[ERROR] No parquet files found for {key} at {meta['path']}")
        return

    print("\n" + "=" * 80)
    print(f"  DATASET SUMMARY: {meta['name']} ({meta['store']})")
    print("=" * 80)
    print(f" Key:         {key}")
    print(f" File Path:   {meta['path']}")
    print(f" File Count:  {len(files):,d} files")
    print(f" Purpose:     {meta['purpose']}")
    print("-" * 80)

    # Fast row count and schema using DuckDB
    hive_opt = ", hive_partitioning=true" if meta["hive"] else ""
    try:
        count_res = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{meta['path']}'{hive_opt})").fetchone()[0]
        print(f" Total Rows:  {count_res:,d}")
    except Exception as e:
        print(f" Row Count:   [Error counting rows: {e}]")

    print("\n Schema & Columns:")
    try:
        describe_df = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{meta['path']}'{hive_opt}) LIMIT 1").df()
        for idx, row in describe_df.iterrows():
            print(f"   {idx+1:>2}. {row['column_name']:<32} : {row['column_type']}")
    except Exception as e:
        print(f"   [Error inspecting schema: {e}]")
    print("=" * 80 + "\n")


def sample_dataset(conn, key, limit=5):
    """Display sample records from a parquet dataset."""
    if key not in DATASET_CATALOG:
        print(f"[ERROR] Unknown dataset key '{key}'. Available keys: {list(DATASET_CATALOG.keys())}")
        return

    meta = DATASET_CATALOG[key]
    hive_opt = ", hive_partitioning=true" if meta["hive"] else ""
    
    # Select sample columns if available, or all
    col_str = ", ".join(meta["sample_columns"]) if "sample_columns" in meta else "*"
    
    print("\n" + "=" * 80)
    print(f"  SAMPLE RECORDS: {meta['name']} (LIMIT {limit})")
    print(f"  Store: {meta['store']} | Key: {key}")
    print("=" * 80)
    try:
        query = f"SELECT {col_str} FROM read_parquet('{meta['path']}'{hive_opt}) LIMIT {limit}"
        df = conn.execute(query).df()
        print(df.to_string(index=False))
    except Exception as e:
        # Fallback to SELECT *
        try:
            df = conn.execute(f"SELECT * FROM read_parquet('{meta['path']}'{hive_opt}) LIMIT {limit}").df()
            print(df.to_string(index=False))
        except Exception as e2:
            print(f"[ERROR] Failed to sample dataset: {e2}")
    print("=" * 80 + "\n")


def interactive_menu(conn):
    """Interactive explorer menu."""
    while True:
        print("\n" + "#" * 55)
        print("   CRICENGINE FEATURE & PREDICTIVE STORE EXPLORER")
        print("#" * 55)
        print("  [1] List all Parquet datasets and file counts")
        print("  [2] View dataset summary & schema")
        print("  [3] Inspect sample records from a dataset")
        print("  [4] Inspect end-to-end match features (Match 1389392)")
        print("  [0] Exit")
        print("#" * 55)

        choice = input("Enter choice (0-4): ").strip()
        if choice == "0":
            print("\nExiting feature explorer. Good luck!\n")
            break
        elif choice == "1":
            list_datasets(conn)
        elif choice == "2":
            list_datasets(conn)
            k = input("Enter dataset key: ").strip()
            show_dataset_summary(conn, k)
        elif choice == "3":
            list_datasets(conn)
            k = input("Enter dataset key: ").strip()
            lim = input("Enter number of sample rows [default 5]: ").strip()
            limit = int(lim) if lim.isdigit() else 5
            sample_dataset(conn, k, limit)
        elif choice == "4":
            inspect_sample_match(conn)
        else:
            print("[!] Invalid selection.")


def inspect_sample_match(conn):
    """Showcase end-to-end features and predictions for Match 1389392."""
    mid = "1389392"
    print("\n" + "=" * 80)
    print(f"  END-TO-END FEATURE TRACE: MATCH {mid} (IND vs AUS, T20I)")
    print("=" * 80)

    # 1. Feature Store Player Performance
    print("\n[A] Feature Store (player_match) — Transformed Match Stats:")
    q_pm = f"""
    SELECT 
        pm.player_id,
        pm.runs_scored,
        pm.balls_faced,
        pm.strike_rate,
        pm.overs_bowled,
        pm.runs_conceded,
        pm.wickets_credited,
        pm.economy_rate
    FROM read_parquet('{DATASET_CATALOG["fs_player_match"]["path"]}', hive_partitioning=true) pm
    WHERE pm.match_id = '{mid}'
    ORDER BY pm.runs_scored DESC
    LIMIT 5;
    """
    print(conn.execute(q_pm).df().to_string(index=False))

    # 2. Rating Store Pre-Match Snapshots
    print("\n[B] Rating Store (pre_match_snapshots) — Zero-Leakage Pre-Match Ratings:")
    q_rs = f"""
    SELECT 
        rs.player_id,
        rs.inferred_role,
        ROUND(rs.pre_r_bat, 2) AS pre_r_bat,
        ROUND(rs.pre_rd_bat, 2) AS pre_rd_bat,
        ROUND(rs.pre_r_bowl, 2) AS pre_r_bowl,
        ROUND(rs.pre_rd_bowl, 2) AS pre_rd_bowl,
        ROUND(rs.pre_vorp, 2) AS pre_vorp
    FROM read_parquet('{DATASET_CATALOG["rs_pre_match"]["path"]}', hive_partitioning=true) rs
    WHERE rs.match_id = '{mid}'
    ORDER BY rs.pre_vorp DESC
    LIMIT 5;
    """
    print(conn.execute(q_rs).df().to_string(index=False))

    # 3. Predictive Store VORP
    print("\n[C] Predictive Store (player_match_vorp) — Post-Match VORP Impact:")
    q_ps = f"""
    SELECT 
        ps.player_id,
        ps.inferred_role,
        ROUND(ps.vorp_bat, 2) AS vorp_bat,
        ROUND(ps.vorp_bowl, 2) AS vorp_bowl,
        ROUND(ps.vorp_field, 2) AS vorp_field,
        ROUND(ps.vorp_total, 2) AS vorp_total,
        ps.is_above_replacement
    FROM read_parquet('{DATASET_CATALOG["ps_vorp"]["path"]}', hive_partitioning=true) ps
    WHERE ps.match_id = '{mid}'
    ORDER BY ps.vorp_total DESC
    LIMIT 5;
    """
    print(conn.execute(q_ps).df().to_string(index=False))
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="CricEngine AI - Parquet Feature & Predictive Store Explorer")
    parser.add_argument("--list", action="store_true", help="List all datasets in catalog")
    parser.add_argument("--summary", type=str, help="Show schema and summary for specified dataset key")
    parser.add_argument("--sample", type=str, help="Sample records from specified dataset key")
    parser.add_argument("--limit", type=int, default=5, help="Number of records to sample (default: 5)")
    parser.add_argument("--demo-match", action="store_true", help="Inspect end-to-end features for Match 1389392")
    args = parser.parse_args()

    # Open in-memory DuckDB instance to query parquet files
    conn = duckdb.connect()

    if args.list:
        list_datasets(conn)
    elif args.summary:
        show_dataset_summary(conn, args.summary)
    elif args.sample:
        sample_dataset(conn, args.sample, args.limit)
    elif args.demo_match:
        inspect_sample_match(conn)
    else:
        if sys.stdin.isatty():
            interactive_menu(conn)
        else:
            list_datasets(conn)

    conn.close()


if __name__ == "__main__":
    main()
