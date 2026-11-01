"""
Phase 4B.2 Workstream A: Identical-Population Baseline Reconciliation Script.
Compares BM-0, BM-1, BM-2, and CA-HBSS on precisely the same unique observations,
stratified by player experience tiers (Debutant, Moderate, Established) and format.
"""

import json
import math
import os
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUTPUT_DIR = "data/analysis/phase_4b_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def compute_crps_point(pred_mean: float, pred_std: float, actual_y: float) -> float:
    """Computes exact Continuous Ranked Probability Score (CRPS) for Gaussian predictive distribution."""
    if pred_std <= 1e-6:
        return abs(actual_y - pred_mean)
    z = (actual_y - pred_mean) / pred_std
    phi_z = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    Phi_z = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return max(0.0, pred_std * (z * (2.0 * Phi_z - 1.0) + 2.0 * phi_z - 1.0 / math.sqrt(math.pi)))


def evaluate_model_metrics(df, actual_col, pred_col, std_col=None):
    """Computes MAE, RMSE, Mean Pred, Mean Actual, Bias, and CRPS."""
    valid = df.dropna(subset=[actual_col, pred_col])
    if len(valid) == 0:
        return {"n": 0, "mae": np.nan, "rmse": np.nan, "bias": np.nan, "mean_pred": np.nan, "mean_actual": np.nan, "crps": np.nan}
    
    act = valid[actual_col].values
    pred = valid[pred_col].values
    err = act - pred
    
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    bias = float(np.mean(pred - act))
    mean_pred = float(np.mean(pred))
    mean_act = float(np.mean(act))
    
    if std_col and std_col in valid.columns:
        stds = valid[std_col].values
        crps = float(np.mean([compute_crps_point(p, s, a) for p, s, a in zip(pred, stds, act)]))
    else:
        # Fallback std ~ sample rmse
        crps = float(np.mean([compute_crps_point(p, rmse, a) for p, a in zip(pred, act)]))
        
    return {
        "n": len(valid),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "bias": round(bias, 3),
        "mean_pred": round(mean_pred, 3),
        "mean_actual": round(mean_act, 3),
        "crps": round(crps, 3)
    }


def main():
    print("=== WORKSTREAM A: IDENTICAL-POPULATION BASELINE RECONCILIATION ===")

    # 1. Load Pre-Match Snapshots (Holdout 2020-2024)
    snap_ds = ds.dataset("data/datalake/rating_store_v4/pre_match_snapshots", partitioning="hive")
    snap_df = snap_ds.to_table().to_pandas()
    snap_df["date"] = pd.to_datetime(snap_df["match_date"])
    holdout_snaps = snap_df[(snap_df["date"] >= "2020-01-01") & (snap_df["date"] <= "2024-12-31")].copy()

    # 2. Load Player Match (Holdout 2020-2024)
    pm_ds = ds.dataset("data/datalake/feature_store_v3b/player_match", partitioning="hive")
    pm_df = pm_ds.to_table(columns=[
        "match_id", "player_id", "start_date", "match_format",
        "runs_scored", "balls_faced", "is_dismissed",
        "legal_balls_bowled", "runs_conceded", "wickets_credited"
    ]).to_pandas()

    # 3. Load Rolling Match (FILTER window_size == 10 to prevent Cartesian explosion)
    rm_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_match", partitioning="hive")
    rm_df = rm_ds.to_table(
        filter=ds.field("window_size") == 10,
        columns=["match_id", "player_id", "rolling_batting_sr", "rolling_economy_rate", "matches_in_window"]
    ).to_pandas()

    # 4. Load Rolling Time (FILTER window_days == 365 to prevent Cartesian explosion)
    rt_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_time", partitioning="hive")
    rt_df = rt_ds.to_table(
        filter=ds.field("window_days") == 365,
        columns=["match_id", "player_id", "decayed_batting_sr", "decayed_economy_rate"]
    ).to_pandas()

    # 5. Compute Prior Matches per player up to match_date (from full player_match dataset)
    print("Computing cumulative prior appearances per player...")
    all_pm = pm_ds.to_table(columns=["match_id", "player_id", "start_date", "match_format"]).to_pandas()
    all_pm["start_date"] = pd.to_datetime(all_pm["start_date"])
    all_pm = all_pm.sort_values(["player_id", "start_date", "match_id"])
    
    # Cumulative prior matches in career and in format
    all_pm["career_matches_prior"] = all_pm.groupby("player_id").cumcount()
    all_pm["format_matches_prior"] = all_pm.groupby(["player_id", "match_format"]).cumcount()
    
    prior_counts = all_pm[["match_id", "player_id", "career_matches_prior", "format_matches_prior"]]

    # 6. Merge unique holdout 1-to-1 dataset
    df = pd.merge(holdout_snaps, pm_df, on=["match_id", "player_id"], suffixes=("", "_pm"))
    df = pd.merge(df, rm_df, on=["match_id", "player_id"], how="left")
    df = pd.merge(df, rt_df, on=["match_id", "player_id"], how="left")
    df = pd.merge(df, prior_counts, on=["match_id", "player_id"], how="left")

    print(f"Total Unique 1-to-1 Holdout Participations: {len(df):,}")

    # Experience Tiers based on format_matches_prior (strictly chronological prior appearances)
    df["exp_tier"] = pd.cut(
        df["format_matches_prior"].fillna(0),
        bins=[-1, 4, 9, 9999],
        labels=["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]
    )

    # Career Experience Tier (alternative check)
    df["career_exp_tier"] = pd.cut(
        df["career_matches_prior"].fillna(0),
        bins=[-1, 4, 9, 9999],
        labels=["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]
    )

    # =========================================================================
    # PART 1: BATTING RECONCILIATION (Unique active batting innings: balls_faced > 0)
    # =========================================================================
    bat_df = df[df["balls_faced"].fillna(0) > 0].copy()
    bat_df["actual_runs"] = bat_df["runs_scored"].astype(float)
    bat_df["b_faced"] = bat_df["balls_faced"].astype(float)

    format_base_sr = {"T20": 135.0, "ODI": 88.0, "TEST": 53.0}

    # BM-0: Population Average
    bat_df["bm0_pred_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (format_base_sr.get(str(r["match_format"]).upper(), 100.0) / 100.0), axis=1
    )

    # BM-1 Pure: Rolling 10-match (NaN if no historical batting)
    bat_df["bm1_pure_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (r["rolling_batting_sr"] / 100.0) if pd.notna(r["rolling_batting_sr"]) and r["rolling_batting_sr"] > 0 else np.nan, axis=1
    )
    # BM-1 Fallback: Falls back to BM-0 when missing
    bat_df["bm1_pred_runs"] = bat_df["bm1_pure_runs"].fillna(bat_df["bm0_pred_runs"])

    # BM-2 Pure: EWMA 365-day (NaN if no historical batting)
    bat_df["bm2_pure_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (r["decayed_batting_sr"] / 100.0) if pd.notna(r["decayed_batting_sr"]) and r["decayed_batting_sr"] > 0 else np.nan, axis=1
    )
    # BM-2 Fallback: Falls back to BM-1 / BM-0 when missing
    bat_df["bm2_pred_runs"] = bat_df["bm2_pure_runs"].fillna(bat_df["bm1_pred_runs"])

    # CA-HBSS Prediction
    bat_df["cahbss_z"] = (bat_df["pre_r_bat"] - 1000.0) / (350.0 * 0.50)
    bat_df["cahbss_pred_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (format_base_sr.get(str(r["match_format"]).upper(), 100.0) / 100.0) * math.exp(max(-1.0, min(1.0, r["cahbss_z"] * 0.35))), axis=1
    )
    # Approximate predictive standard deviation
    bat_df["cahbss_pred_std"] = bat_df.apply(
        lambda r: math.sqrt(0.25 * (r["cahbss_pred_runs"]**2) + r["cahbss_pred_runs"] + 1.0) + (r["pre_rd_bat"] / 350.0) * 5.0, axis=1
    )

    print(f"\n--- BATTING EVALUATION ON UNIQUE INNINGS (N = {len(bat_df):,}) ---")
    
    bat_models = [
        ("BM-0: Population Average", "bm0_pred_runs"),
        ("BM-1: Rolling Average (Fallback)", "bm1_pred_runs"),
        ("BM-2: Recency-Weighted EWMA (Fallback)", "bm2_pred_runs"),
        ("CA-HBSS Rating Engine", "cahbss_pred_runs"),
    ]

    # Evaluate Overall
    bat_overall_res = []
    for name, col in bat_models:
        m = evaluate_model_metrics(bat_df, "actual_runs", col, "cahbss_pred_std" if "CA-HBSS" in name else None)
        bat_overall_res.append({"Model": name, **m})
    print("\nOVERALL BATTING METRICS:")
    print(pd.DataFrame(bat_overall_res).to_string(index=False))

    # Evaluate By Experience Tier (Format Matches Prior)
    bat_tier_results = []
    for tier in ["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]:
        tier_sub = bat_df[bat_df["exp_tier"] == tier]
        for name, col in bat_models:
            m = evaluate_model_metrics(tier_sub, "actual_runs", col, "cahbss_pred_std" if "CA-HBSS" in name else None)
            bat_tier_results.append({"Tier": tier, "Model": name, **m})
    print("\nBATTING METRICS BY FORMAT EXPERIENCE TIER:")
    print(pd.DataFrame(bat_tier_results).to_string(index=False))

    # Evaluate On Pure Available Subsets (No Fallback)
    print("\nEVALUATING ON PURE AVAILABLE SUBSETS (No Fallback to Population Mean):")
    pure_sub = bat_df.dropna(subset=["bm1_pure_runs", "bm2_pure_runs"])
    print(f"Observations where both BM-1 and BM-2 exist: {len(pure_sub):,} / {len(bat_df):,}")
    pure_res = []
    for name, col in [("BM-0", "bm0_pred_runs"), ("BM-1 Pure", "bm1_pure_runs"), ("BM-2 Pure", "bm2_pure_runs"), ("CA-HBSS", "cahbss_pred_runs")]:
        m = evaluate_model_metrics(pure_sub, "actual_runs", col)
        pure_res.append({"Model": name, **m})
    print(pd.DataFrame(pure_res).to_string(index=False))

    # Cold-Start Specific Evaluation (Debutant with 0 prior format matches)
    cold_start_sub = bat_df[bat_df["format_matches_prior"] == 0]
    print(f"\nCOLD-START DEBUTANTS (0 prior format matches, N = {len(cold_start_sub):,}):")
    cold_res = []
    for name, col in [("BM-0 (Population)", "bm0_pred_runs"), ("BM-1 (Fallback=BM0)", "bm1_pred_runs"), ("CA-HBSS", "cahbss_pred_runs")]:
        m = evaluate_model_metrics(cold_start_sub, "actual_runs", col)
        cold_res.append({"Model": name, **m})
    print(pd.DataFrame(cold_res).to_string(index=False))

    # =========================================================================
    # PART 2: BOWLING RECONCILIATION (Unique active bowling spells: legal_balls > 0)
    # =========================================================================
    bowl_df = df[df["legal_balls_bowled"].fillna(0) > 0].copy()
    bowl_df["actual_wkts"] = bowl_df["wickets_credited"].astype(float)
    bowl_df["actual_runs_conceded"] = bowl_df["runs_conceded"].astype(float)
    bowl_df["b_bowled"] = bowl_df["legal_balls_bowled"].astype(float)

    format_base_haz = {"T20": 0.035, "ODI": 0.030, "TEST": 0.028}
    format_base_econ = {"T20": 8.00, "ODI": 5.40, "TEST": 3.20}

    # BM-0
    bowl_df["bm0_pred_wkts"] = bowl_df.apply(
        lambda r: r["b_bowled"] * format_base_haz.get(str(r["match_format"]).upper(), 0.032), axis=1
    )
    bowl_df["bm0_pred_econ_runs"] = bowl_df.apply(
        lambda r: r["b_bowled"] * (format_base_econ.get(str(r["match_format"]).upper(), 6.0) / 6.0), axis=1
    )

    # BM-1 Pure
    bowl_df["bm1_pure_econ_runs"] = bowl_df.apply(
        lambda r: r["b_bowled"] * (r["rolling_economy_rate"] / 6.0) if pd.notna(r["rolling_economy_rate"]) and r["rolling_economy_rate"] > 0 else np.nan, axis=1
    )
    bowl_df["bm1_pred_econ_runs"] = bowl_df["bm1_pure_econ_runs"].fillna(bowl_df["bm0_pred_econ_runs"])
    bowl_df["bm1_pred_wkts"] = bowl_df["bm0_pred_wkts"]  # Feature store lacks rolling strike rate in minimal schema

    # BM-2 Pure
    bowl_df["bm2_pure_econ_runs"] = bowl_df.apply(
        lambda r: r["b_bowled"] * (r["decayed_economy_rate"] / 6.0) if pd.notna(r["decayed_economy_rate"]) and r["decayed_economy_rate"] > 0 else np.nan, axis=1
    )
    bowl_df["bm2_pred_econ_runs"] = bowl_df["bm2_pure_econ_runs"].fillna(bowl_df["bm1_pred_econ_runs"])

    # CA-HBSS
    bowl_df["cahbss_bowl_z"] = (bowl_df["pre_r_bowl"] - 1000.0) / (350.0 * 0.50)
    bowl_df["cahbss_pred_wkts"] = bowl_df.apply(
        lambda r: r["b_bowled"] * format_base_haz.get(str(r["match_format"]).upper(), 0.032) * math.exp(max(-1.0, min(1.0, r["cahbss_bowl_z"] * 0.30))), axis=1
    )
    bowl_df["cahbss_pred_econ_runs"] = bowl_df.apply(
        lambda r: r["b_bowled"] * (format_base_econ.get(str(r["match_format"]).upper(), 6.0) / 6.0) * math.exp(max(-1.0, min(1.0, -r["cahbss_bowl_z"] * 0.20))), axis=1
    )
    bowl_df["cahbss_wkt_std"] = np.sqrt(bowl_df["cahbss_pred_wkts"] + 0.20 * (bowl_df["cahbss_pred_wkts"]**2))

    print(f"\n--- BOWLING EVALUATION ON UNIQUE SPELLS (N = {len(bowl_df):,}) ---")

    # Wickets
    bowl_wkt_models = [
        ("BM-0: Population Average", "bm0_pred_wkts"),
        ("BM-1: Rolling Baseline", "bm1_pred_wkts"),
        ("CA-HBSS Rating Engine", "cahbss_pred_wkts"),
    ]
    bowl_overall_wkt_res = []
    for name, col in bowl_wkt_models:
        m = evaluate_model_metrics(bowl_df, "actual_wkts", col, "cahbss_wkt_std" if "CA-HBSS" in name else None)
        bowl_overall_wkt_res.append({"Model": name, **m})
    print("\nOVERALL BOWLING WICKETS:")
    print(pd.DataFrame(bowl_overall_wkt_res).to_string(index=False))

    # Runs Conceded
    bowl_econ_models = [
        ("BM-0: Population Average", "bm0_pred_econ_runs"),
        ("BM-1: Rolling Average (Fallback)", "bm1_pred_econ_runs"),
        ("BM-2: Recency EWMA (Fallback)", "bm2_pred_econ_runs"),
        ("CA-HBSS Rating Engine", "cahbss_pred_econ_runs"),
    ]
    bowl_overall_econ_res = []
    for name, col in bowl_econ_models:
        m = evaluate_model_metrics(bowl_df, "actual_runs_conceded", col)
        bowl_overall_econ_res.append({"Model": name, **m})
    print("\nOVERALL BOWLING RUNS CONCEDED:")
    print(pd.DataFrame(bowl_overall_econ_res).to_string(index=False))

    # Bowling by Experience Tier
    bowl_tier_results = []
    for tier in ["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]:
        tier_sub = bowl_df[bowl_df["exp_tier"] == tier]
        for name, col in bowl_wkt_models:
            m = evaluate_model_metrics(tier_sub, "actual_wkts", col, "cahbss_wkt_std" if "CA-HBSS" in name else None)
            bowl_tier_results.append({"Tier": tier, "Discipline": "Wickets", "Model": name, **m})
        for name, col in bowl_econ_models:
            m = evaluate_model_metrics(tier_sub, "actual_runs_conceded", col)
            bowl_tier_results.append({"Tier": tier, "Discipline": "Runs Conceded", "Model": name, **m})
    print("\nBOWLING METRICS BY FORMAT EXPERIENCE TIER:")
    print(pd.DataFrame(bowl_tier_results).to_string(index=False))

    # By Format Evaluation
    format_results = []
    for fmt in ["T20", "ODI", "TEST"]:
        f_bat = bat_df[bat_df["match_format"].str.upper() == fmt]
        for name, col in bat_models:
            m = evaluate_model_metrics(f_bat, "actual_runs", col)
            format_results.append({"Format": fmt, "Discipline": "Batting Runs", "Model": name, **m})
        f_bowl = bowl_df[bowl_df["match_format"].str.upper() == fmt]
        for name, col in bowl_wkt_models:
            m = evaluate_model_metrics(f_bowl, "actual_wkts", col)
            format_results.append({"Format": fmt, "Discipline": "Bowling Wkts", "Model": name, **m})
        for name, col in bowl_econ_models:
            m = evaluate_model_metrics(f_bowl, "actual_runs_conceded", col)
            format_results.append({"Format": fmt, "Discipline": "Bowling Runs", "Model": name, **m})

    # Save all results to disk
    full_output = {
        "batting_overall": bat_overall_res,
        "batting_by_tier": bat_tier_results,
        "batting_pure_subsets": pure_res,
        "batting_cold_start": cold_res,
        "bowling_wkt_overall": bowl_overall_wkt_res,
        "bowling_econ_overall": bowl_overall_econ_res,
        "bowling_by_tier": bowl_tier_results,
        "by_format": format_results
    }
    with open(os.path.join(OUTPUT_DIR, "baseline_comparison_results.json"), "w") as f:
        json.dump(full_output, f, indent=2)

    pd.DataFrame(bat_tier_results).to_csv(os.path.join(OUTPUT_DIR, "batting_tier_reconciliation.csv"), index=False)
    pd.DataFrame(bowl_tier_results).to_csv(os.path.join(OUTPUT_DIR, "bowling_tier_reconciliation.csv"), index=False)
    pd.DataFrame(format_results).to_csv(os.path.join(OUTPUT_DIR, "format_comparison_results.csv"), index=False)
    print(f"\nAll results saved to {OUTPUT_DIR}/baseline_comparison_results.json and CSVs.")


if __name__ == "__main__":
    main()
