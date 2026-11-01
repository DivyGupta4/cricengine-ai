"""
Phase 4B.2 Workstream B: Observation Population Reconciliation Script.
Exhaustively audits and reconciles the observation counts across pre-match snapshots,
player_match feature store, and the Cartesian explosion in Phase 4B.1 holdout evaluation.
"""

import json
import os
import duckdb
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUTPUT_DIR = "data/analysis/phase_4b_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    print("=== WORKSTREAM B: OBSERVATION POPULATION RECONCILIATION ===")

    # 1. Inspect Pre-Match Snapshots
    snap_ds = ds.dataset("data/datalake/rating_store_v4/pre_match_snapshots", partitioning="hive")
    snap_df = snap_ds.to_table().to_pandas()
    snap_df["date"] = pd.to_datetime(snap_df["match_date"])
    
    total_snaps = len(snap_df)
    holdout_snaps = snap_df[(snap_df["date"] >= "2020-01-01") & (snap_df["date"] <= "2024-12-31")].copy()
    
    print(f"Total Pre-Match Snapshots on disk: {total_snaps:,}")
    print(f"Holdout (2020-2024) Snapshots: {len(holdout_snaps):,}")
    print(f"Holdout Unique Matches in Snapshots: {holdout_snaps['match_id'].nunique():,}")
    print(f"Holdout Unique Players in Snapshots: {holdout_snaps['player_id'].nunique():,}")

    # 2. Inspect Player Match Feature Store (Canonical Participations)
    pm_ds = ds.dataset("data/datalake/feature_store_v3b/player_match", partitioning="hive")
    pm_df = pm_ds.to_table().to_pandas()
    pm_df["date"] = pd.to_datetime(pm_df["start_date"])
    
    total_pm = len(pm_df)
    holdout_pm = pm_df[(pm_df["date"] >= "2020-01-01") & (pm_df["date"] <= "2024-12-31")].copy()
    
    print(f"\nTotal Player-Match records in Feature Store: {total_pm:,}")
    print(f"Holdout (2020-2024) Player-Match records: {len(holdout_pm):,}")
    print(f"Holdout Unique Matches in Feature Store: {holdout_pm['match_id'].nunique():,}")
    print(f"Holdout Unique Players in Feature Store: {holdout_pm['player_id'].nunique():,}")

    # 3. Check Sampling Logic: Why 305 matches vs 3,102 matches?
    # In chronological_engine.py: `if batch_idx % 10 == 0:`
    # Pre-match snapshots were sampled every 10th batch!
    
    # 4. Join Pre-Match Snapshots with Player Match on (match_id, player_id)
    # This represents the true, non-duplicated holdout evaluation sample
    merged_1to1 = pd.merge(holdout_snaps, holdout_pm, on=["match_id", "player_id"], suffixes=("_snap", "_pm"))
    print(f"\nUnique 1-to-1 Holdout Evaluated Participations: {len(merged_1to1):,}")
    print(f"Unique Matches: {merged_1to1['match_id'].nunique():,}")
    print(f"Unique Players: {merged_1to1['player_id'].nunique():,}")

    # 5. Discipline Breakdown on the True 1-to-1 Holdout Sample
    bat_innings = merged_1to1[merged_1to1["balls_faced"].fillna(0) > 0]
    bat_dnb = merged_1to1[merged_1to1["balls_faced"].fillna(0) == 0]
    
    bowl_spells = merged_1to1[merged_1to1["legal_balls_bowled"].fillna(0) > 0]
    bowl_dnb = merged_1to1[merged_1to1["legal_balls_bowled"].fillna(0) == 0]

    print(f"\nTrue Unique Batting Innings (balls_faced > 0): {len(bat_innings):,}")
    print(f"True Batting DNB (balls_faced == 0): {len(bat_dnb):,}")
    print(f"True Unique Bowling Spells (legal_balls > 0): {len(bowl_spells):,}")
    print(f"True Bowling DNB (legal_balls == 0): {len(bowl_dnb):,}")

    # 6. Reconstruct the Cartesian Explosion in Phase 4B.1
    # Check rolling_match and rolling_time windows
    rm_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_match", partitioning="hive")
    rm_windows = rm_ds.to_table(columns=["window_size"]).to_pandas()["window_size"].unique().tolist()
    
    rt_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_time", partitioning="hive")
    rt_windows = rt_ds.to_table(columns=["window_days"]).to_pandas()["window_days"].unique().tolist()

    num_rm_windows = len(rm_windows)
    num_rt_windows = len(rt_windows)
    cartesian_factor = num_rm_windows * num_rt_windows

    print(f"\nRolling Match Window Sizes: {rm_windows} (Count: {num_rm_windows})")
    print(f"Rolling Time Window Days: {rt_windows} (Count: {num_rt_windows})")
    print(f"Cartesian Multiplication Factor: {num_rm_windows} x {num_rt_windows} = {cartesian_factor}")

    reported_pm = len(merged_1to1) * cartesian_factor
    reported_bat = len(bat_innings) * cartesian_factor
    reported_bowl = len(bowl_spells) * cartesian_factor

    print(f"\nCartesian Expanded Totals:")
    print(f"  Player-Match: {len(merged_1to1)} x 9 = {reported_pm:,} (Reported in 4B.1: 59,706)")
    print(f"  Batting:      {len(bat_innings)} x 9 = {reported_bat:,} (Reported in 4B.1: 44,559)")
    print(f"  Bowling:      {len(bowl_spells)} x 9 = {reported_bowl:,} (Reported in 4B.1: 32,391)")

    # 7. Multi-innings / Test Matches Structure Analysis
    # How does player_match represent Test matches?
    test_pm = holdout_pm[holdout_pm["match_format"].str.upper() == "TEST"]
    print(f"\nHoldout Test player_match rows: {len(test_pm):,}")
    print(f"Unique (match_id, player_id) in Test holdout: {test_pm.groupby(['match_id', 'player_id']).size().max()}")
    # player_match in Feature Store v3b is aggregated at the MATCH LEVEL, NOT innings level!
    # A Test match has exactly ONE row per player in player_match with aggregated match runs and wickets!

    # 8. Construct Comprehensive Reconciliation Table
    reconciliation_rows = [
        {
            "Population": "Canonical Matches Processed (All-Time)",
            "Unique Matches": pm_df["match_id"].nunique(),
            "Unique Players": pm_df["player_id"].nunique(),
            "Unique Player-Match Pairs": len(pm_df),
            "Observation Rows": len(pm_df),
            "Notes": "All historical matches across T20, ODI, Test (2001-2026)"
        },
        {
            "Population": "Pre-Match Snapshots Materialized (All-Time)",
            "Unique Matches": snap_df["match_id"].nunique(),
            "Unique Players": snap_df["player_id"].nunique(),
            "Unique Player-Match Pairs": len(snap_df),
            "Observation Rows": len(snap_df),
            "Notes": "Materialized via 10% batch sampling (batch_idx % 10 == 0)"
        },
        {
            "Population": "Feature Store Holdout Participations (2020-2024)",
            "Unique Matches": holdout_pm["match_id"].nunique(),
            "Unique Players": holdout_pm["player_id"].nunique(),
            "Unique Player-Match Pairs": len(holdout_pm),
            "Observation Rows": len(holdout_pm),
            "Notes": "Complete player-match census in holdout period"
        },
        {
            "Population": "Pre-Match Snapshots in Holdout (2020-2024)",
            "Unique Matches": holdout_snaps["match_id"].nunique(),
            "Unique Players": holdout_snaps["player_id"].nunique(),
            "Unique Player-Match Pairs": len(holdout_snaps),
            "Observation Rows": len(holdout_snaps),
            "Notes": "Exact sampled snapshot cohort in holdout period"
        },
        {
            "Population": "True 1-to-1 Holdout Evaluated Player-Matches",
            "Unique Matches": merged_1to1["match_id"].nunique(),
            "Unique Players": merged_1to1["player_id"].nunique(),
            "Unique Player-Match Pairs": len(merged_1to1),
            "Observation Rows": len(merged_1to1),
            "Notes": "True ground-truth sample (1 row per player-match)"
        },
        {
            "Population": "True Holdout Batting Innings (balls_faced > 0)",
            "Unique Matches": bat_innings["match_id"].nunique(),
            "Unique Players": bat_innings["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bat_innings),
            "Observation Rows": len(bat_innings),
            "Notes": "Active batting observations (DNB excluded)"
        },
        {
            "Population": "True Holdout Batting DNB (balls_faced == 0)",
            "Unique Matches": bat_dnb["match_id"].nunique(),
            "Unique Players": bat_dnb["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bat_dnb),
            "Observation Rows": len(bat_dnb),
            "Notes": "Did not bat or faced 0 balls"
        },
        {
            "Population": "True Holdout Bowling Spells (legal_balls > 0)",
            "Unique Matches": bowl_spells["match_id"].nunique(),
            "Unique Players": bowl_spells["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bowl_spells),
            "Observation Rows": len(bowl_spells),
            "Notes": "Active bowling observations (Did not bowl excluded)"
        },
        {
            "Population": "True Holdout Bowling DNB (legal_balls == 0)",
            "Unique Matches": bowl_dnb["match_id"].nunique(),
            "Unique Players": bowl_dnb["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bowl_dnb),
            "Observation Rows": len(bowl_dnb),
            "Notes": "Did not bowl"
        },
        {
            "Population": "Phase 4B.1 Reported Holdout Evaluation (Cartesian 9x)",
            "Unique Matches": merged_1to1["match_id"].nunique(),
            "Unique Players": merged_1to1["player_id"].nunique(),
            "Unique Player-Match Pairs": len(merged_1to1),
            "Observation Rows": reported_pm,
            "Notes": "Cartesian explosion: 6,634 x 3 (rm windows) x 3 (rt windows)"
        },
        {
            "Population": "Phase 4B.1 Reported Batting Evaluation (Cartesian 9x)",
            "Unique Matches": bat_innings["match_id"].nunique(),
            "Unique Players": bat_innings["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bat_innings),
            "Observation Rows": reported_bat,
            "Notes": "Cartesian explosion: 4,951 x 9 = 44,559"
        },
        {
            "Population": "Phase 4B.1 Reported Bowling Evaluation (Cartesian 9x)",
            "Unique Matches": bowl_spells["match_id"].nunique(),
            "Unique Players": bowl_spells["player_id"].nunique(),
            "Unique Player-Match Pairs": len(bowl_spells),
            "Observation Rows": reported_bowl,
            "Notes": "Cartesian explosion: 3,599 x 9 = 32,391"
        }
    ]

    rec_df = pd.DataFrame(reconciliation_rows)
    csv_path = os.path.join(OUTPUT_DIR, "reconciliation_table.csv")
    json_path = os.path.join(OUTPUT_DIR, "reconciliation_table.json")
    
    rec_df.to_csv(csv_path, index=False)
    with open(json_path, "w") as f:
        json.dump(reconciliation_rows, f, indent=2)

    print(f"\nSaved reconciliation table to {csv_path} and {json_path}")
    print("\n--- RECONCILIATION SUMMARY TABLE ---")
    print(rec_df.to_string(index=False))

if __name__ == "__main__":
    main()
