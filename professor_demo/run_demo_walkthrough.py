#!/usr/bin/env python3
"""
run_demo_walkthrough.py — Guided 8-Step Professor Demonstration Runner for CricEngine AI.

Automates the exact demonstration sequence with live read-only queries and formatted outputs.
Run with:
    .venv/bin/python professor_demo/run_demo_walkthrough.py
"""

import os
import sys
import json
import time

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
except ImportError:
    print("[ERROR] duckdb is missing. Please use: .venv/bin/python professor_demo/run_demo_walkthrough.py")
    sys.exit(1)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "datalake", "curated", "cricengine.duckdb")
RAW_SAMPLE_PATH = os.path.join(PROJECT_ROOT, "data", "raw_cricsheet", "extracted", "t20s_male", "1389392.json")
FEATURE_PATH = os.path.join(PROJECT_ROOT, "data", "datalake", "feature_store_v3b")
RATING_PATH = os.path.join(PROJECT_ROOT, "data", "datalake", "rating_store_v4")
PREDICT_PATH = os.path.join(PROJECT_ROOT, "data", "datalake", "predictive_store_v4c")

DEMO_MATCH_ID = "1389392"


def header(title):
    print("\n" + "#" * 80)
    print(f"  {title.upper()}")
    print("#" * 80 + "\n")


def subheader(title):
    print("\n" + "=" * 80)
    print(f"  >>> {title}")
    print("=" * 80)


def pause(step_num, title):
    print(f"\n[DEMO STEP {step_num}/8] Next: {title}")
    try:
        input("Press [ENTER] to continue (or Ctrl+C to stop)... ")
    except KeyboardInterrupt:
        print("\nDemo cancelled by user.")
        sys.exit(0)


def main():
    header("CricEngine AI — Official Professor Demonstration Walkthrough")
    print("Welcome! This script will guide you step-by-step through the 8-stage data lake demonstration.")
    print(f"Working Directory: {PROJECT_ROOT}")
    print(f"Canonical DB:      {DB_PATH} (Strictly Read-Only)")
    print(f"Featured Match:    ID {DEMO_MATCH_ID} (India vs Australia, T20 International, 2023-11-26)")

    # Connect to DuckDB read-only
    conn = duckdb.connect(database=DB_PATH, read_only=True)

    # =========================================================================
    # STEP 1: Show Raw Cricsheet JSON File
    # =========================================================================
    pause(1, "Show Raw Cricsheet JSON File (Source Ingestion)")
    subheader("Step 1: Raw JSON Ingestion (Cricsheet Spec v1.0.0)")
    print(f"Inspecting original raw match file: {os.path.relpath(RAW_SAMPLE_PATH, PROJECT_ROOT)}")
    if os.path.exists(RAW_SAMPLE_PATH):
        with open(RAW_SAMPLE_PATH) as f:
            raw_data = json.load(f)
        print("\n1. Match Metadata & Event Info:")
        print(f"   Competition: {raw_data['info'].get('event', {}).get('name')}")
        print(f"   Teams:       {raw_data['info'].get('teams')}")
        print(f"   Venue:       {raw_data['info'].get('venue')}, {raw_data['info'].get('city')}")
        print(f"   Outcome:     Winner = {raw_data['info'].get('outcome', {}).get('winner')}, By = {raw_data['info'].get('outcome', {}).get('by')}")
        print(f"   Innings:     {len(raw_data.get('innings', []))} innings recorded in nested JSON tree")
        
        # Show first delivery of 1st innings
        innings_1 = raw_data['innings'][0]
        first_over = innings_1['overs'][0]
        first_delivery = first_over['deliveries'][0]
        print("\n2. First Delivery JSON Object (Nested):")
        print(json.dumps(first_delivery, indent=4))
        print("\nArchitectural takeaway: Nested JSON is flexible for ingestion, but unindexed,")
        print("redundant, and computationally prohibitive for complex analytical aggregations.")
    else:
        print("[!] Raw file not found at expected path.")

    # =========================================================================
    # STEP 2: Canonical DuckDB Relational Schema
    # =========================================================================
    pause(2, "Open Canonical DuckDB and Display 14 Relational Tables")
    subheader("Step 2: Canonical DuckDB Relational Tables (Normalized 3NF Model)")
    print("Database opened in read_only=True mode. Zero risk to canonical storage.\n")
    
    tables_query = """
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'main' 
    ORDER BY table_name;
    """
    tables = [r[0] for r in conn.execute(tables_query).fetchall()]
    
    print(f" {'#':<3} | {'Table Name':<32} | {'Row Count':>15} | {'Schema Type':<15}")
    print("-" * 74)
    total_rows = 0
    for idx, t in enumerate(tables, 1):
        cnt = conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        total_rows += cnt
        stype = "Dimension" if t.startswith("dim_") else ("Fact" if t.startswith("fact_") else "Metadata / Quality")
        print(f" {idx:<3} | {t:<32} | {cnt:>15,d} | {stype:<15}")
    print("-" * 74)
    print(f" Total Canonical Tables: {len(tables)} | Total Lakehouse Relational Rows: {total_rows:,d}")
    print("\nArchitectural takeaway: Raw nested trees are parsed into a clean third normal form (3NF)")
    print("relational schema optimized for fast vectorized columnar analytics and zero duplication.")

    # =========================================================================
    # STEP 3: Query Deliveries for Match 1389392
    # =========================================================================
    pause(3, "Query Match-Level Overview & Ball-by-Ball Deliveries")
    subheader(f"Step 3: Relational Execution — Deliveries for Match {DEMO_MATCH_ID}")
    
    q_deliv = f"""
    SELECT 
        b.innings_num,
        b.over_num,
        b.delivery_num,
        bat.canonical_name AS batter,
        bowl.canonical_name AS bowler,
        b.runs_batter,
        b.runs_extras,
        b.runs_total,
        b.is_wicket
    FROM fact_ball_by_ball b
    JOIN dim_player_master bat ON b.batter_id = bat.player_id
    JOIN dim_player_master bowl ON b.bowler_id = bowl.player_id
    WHERE b.match_id = '{DEMO_MATCH_ID}' AND b.innings_num = 1 AND b.over_num = 0
    ORDER BY b.delivery_num;
    """
    print("Executing query on fact_ball_by_ball joined with dim_player_master:")
    df_deliv = conn.execute(q_deliv).df()
    print(df_deliv.to_string(index=False))
    print(f"\n({len(df_deliv)} legal and extra deliveries in over 1)")

    # =========================================================================
    # STEP 4: Player Participation & Dismissal Records
    # =========================================================================
    pause(4, "Show Player Participation & Dismissal Attribution")
    subheader(f"Step 4: Roster Participation & Dismissals with Fielder Attribution")
    
    print("\n[A] Starting XI Roster Sample (fact_match_participation):")
    q_part = f"""
    SELECT 
        p.team_name,
        pm.canonical_name,
        p.participation_role,
        p.in_starting_xi,
        p.batted_flag,
        p.bowled_flag,
        p.fielded_flag
    FROM fact_match_participation p
    JOIN dim_player_master pm ON p.player_id = pm.player_id
    WHERE p.match_id = '{DEMO_MATCH_ID}'
    ORDER BY p.team_name, pm.canonical_name
    LIMIT 6;
    """
    print(conn.execute(q_part).df().to_string(index=False))

    print("\n[B] Wicket Dismissals & Fielder Involvement (fact_delivery_dismissal + fact_dismissal_fielder):")
    q_dism = f"""
    SELECT 
        d.innings_num,
        out_p.canonical_name AS player_out,
        d.dismissal_kind,
        bowl_p.canonical_name AS bowler,
        COALESCE(f_p.canonical_name, 'Unassisted') AS fielder
    FROM fact_delivery_dismissal d
    JOIN dim_player_master out_p ON d.player_out_id = out_p.player_id
    JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
    JOIN dim_player_master bowl_p ON b.bowler_id = bowl_p.player_id
    LEFT JOIN fact_dismissal_fielder f ON d.dismissal_id = f.dismissal_id
    LEFT JOIN dim_player_master f_p ON f.fielder_id = f_p.player_id
    WHERE d.match_id = '{DEMO_MATCH_ID}'
    ORDER BY d.innings_num, d.dismissal_seq
    LIMIT 6;
    """
    print(conn.execute(q_dism).df().to_string(index=False))
    print("\nArchitectural takeaway: Complex multi-entity cricket relationships (e.g. bowler + fielder")
    print("co-attributions) are normalized with strict referential integrity.")

    # =========================================================================
    # STEP 5: Parquet Feature Store (player_match & rolling_match)
    # =========================================================================
    pause(5, "Inspect Parquet Feature Store (Single Match & Rolling Windows)")
    subheader("Step 5: Parquet Feature Store (feature_store_v3b)")
    
    print("\n[A] Single-Match Transformed Features (player_match):")
    q_fs = f"""
    SELECT 
        pm.canonical_name,
        f.team_name,
        f.batting_position,
        f.runs_scored,
        f.balls_faced,
        ROUND(f.strike_rate, 1) AS strike_rate,
        f.overs_bowled,
        f.wickets_credited,
        f.economy_rate,
        f.catches_taken
    FROM read_parquet('{FEATURE_PATH}/player_match/**/*.parquet', hive_partitioning=true) f
    JOIN dim_player_master pm ON f.player_id = pm.player_id
    WHERE f.match_id = '{DEMO_MATCH_ID}'
    ORDER BY f.runs_scored DESC
    LIMIT 5;
    """
    print(conn.execute(q_fs).df().to_string(index=False))

    print("\n[B] Multi-Window Rolling Form (rolling_match: 5, 10, 20 Match Moving Windows):")
    q_rm = f"""
    SELECT 
        pm.canonical_name,
        rm.window_size,
        rm.matches_in_window,
        rm.rolling_runs_scored,
        ROUND(rm.rolling_batting_avg, 2) AS rolling_avg,
        ROUND(rm.rolling_batting_sr, 1) AS rolling_sr,
        rm.rolling_wickets_taken
    FROM read_parquet('{FEATURE_PATH}/rolling_match/**/*.parquet', hive_partitioning=true) rm
    JOIN dim_player_master pm ON rm.player_id = pm.player_id
    WHERE rm.match_id = '{DEMO_MATCH_ID}' AND pm.canonical_name IN ('SA Yadav', 'GJ Maxwell')
    ORDER BY pm.canonical_name, rm.window_size;
    """
    print(conn.execute(q_rm).df().to_string(index=False))
    print("\nArchitectural takeaway: Parquet feature store supports instantaneous feature retrieval")
    print("with exponential decay and Bayesian shrinkage, partitioned by format, season, and window.")

    # =========================================================================
    # STEP 6: Rating Store (Pre-Match Snapshots)
    # =========================================================================
    pause(6, "Inspect Rating Store (Pre-Match Latent Skill Snapshots)")
    subheader("Step 6: Player Rating Store (rating_store_v4)")
    print("Displaying D-1 Pre-Match Latent Ratings (Frozen prior to match toss):\n")
    
    q_rate = f"""
    SELECT 
        pm.canonical_name,
        s.inferred_role,
        ROUND(s.pre_r_bat, 1) AS pre_rating_bat,
        ROUND(s.pre_rd_bat, 1) AS uncertainty_bat,
        ROUND(s.pre_r_bowl, 1) AS pre_rating_bowl,
        ROUND(s.pre_rd_bowl, 1) AS uncertainty_bowl,
        ROUND(s.pre_vorp, 2) AS pre_match_expected_vorp
    FROM read_parquet('{RATING_PATH}/pre_match_snapshots/**/*.parquet', hive_partitioning=true) s
    JOIN dim_player_master pm ON s.player_id = pm.player_id
    WHERE s.match_id = '{DEMO_MATCH_ID}'
    ORDER BY s.pre_vorp DESC
    LIMIT 6;
    """
    print(conn.execute(q_rate).df().to_string(index=False))
    print("\nArchitectural takeaway: Zero-leakage guarantee. Each player's latent rating (r) and")
    print("epistemic uncertainty (rd) are frozen strictly before the match begins.")

    # =========================================================================
    # STEP 7: Predictive Store (VORP Impact)
    # =========================================================================
    pause(7, "Inspect Predictive Store (Value Over Replacement Player)")
    subheader("Step 7: Predictive Store (predictive_store_v4c)")
    print("Evaluating post-match VORP against role replacement baselines:\n")
    
    q_vorp = f"""
    SELECT 
        pm.canonical_name,
        v.inferred_role,
        ROUND(v.vorp_bat, 2) AS vorp_bat,
        ROUND(v.vorp_bowl, 2) AS vorp_bowl,
        ROUND(v.vorp_field, 2) AS vorp_field,
        ROUND(v.vorp_total, 2) AS vorp_total,
        v.is_above_replacement
    FROM read_parquet('{PREDICT_PATH}/player_match_vorp/**/*.parquet', hive_partitioning=true) v
    JOIN dim_player_master pm ON v.player_id = pm.player_id
    WHERE v.match_id = '{DEMO_MATCH_ID}'
    ORDER BY v.vorp_total DESC
    LIMIT 6;
    """
    print(conn.execute(q_vorp).df().to_string(index=False))
    print("\nArchitectural takeaway: VORP isolates each player's marginal surplus over replacement,")
    print("accounting for player role, format baseline, and contextual leverage.")

    # =========================================================================
    # STEP 8: End-to-End Lineage Explanation
    # =========================================================================
    pause(8, "Explain Full End-to-End Data Lineage")
    subheader("Step 8: End-to-End Multi-Store Unified Analytical Join")
    print("Demonstrating unified query spanning Relational DB + Feature Store + Rating Store + Predictive Store:\n")
    
    q_lineage = f"""
    SELECT 
        pm.canonical_name,
        p.team_name,
        s.inferred_role,
        f.runs_scored,
        f.balls_faced,
        f.wickets_credited,
        ROUND(s.pre_r_bat, 1) AS pre_bat_rating,
        ROUND(s.pre_r_bowl, 1) AS pre_bowl_rating,
        ROUND(v.vorp_total, 2) AS total_match_vorp
    FROM fact_match_participation p
    JOIN dim_player_master pm ON p.player_id = pm.player_id
    JOIN read_parquet('{FEATURE_PATH}/player_match/**/*.parquet', hive_partitioning=true) f 
        ON p.match_id = f.match_id AND p.player_id = f.player_id
    JOIN read_parquet('{RATING_PATH}/pre_match_snapshots/**/*.parquet', hive_partitioning=true) s 
        ON p.match_id = s.match_id AND p.player_id = s.player_id
    JOIN read_parquet('{PREDICT_PATH}/player_match_vorp/**/*.parquet', hive_partitioning=true) v 
        ON p.match_id = v.match_id AND p.player_id = v.player_id
    WHERE p.match_id = '{DEMO_MATCH_ID}'
    ORDER BY v.vorp_total DESC
    LIMIT 8;
    """
    print(conn.execute(q_lineage).df().to_string(index=False))

    conn.close()

    header("Demonstration Complete")
    print("You have successfully showcased the end-to-end CricEngine AI architecture!")
    print("All 8 stages executed successfully against production read-only datasets.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
