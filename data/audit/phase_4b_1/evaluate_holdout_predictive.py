"""
CricEngine AI — Out-of-Sample Predictive Evaluation Engine (Phase 4B.1 Audit)
Evaluates CA-HBSS against BM-0 (Population Mean), BM-1 (Rolling Mean), and BM-2 (EWMA).
"""

import math
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.dataset as ds


def compute_crps_point(pred_mean: float, pred_std: float, actual_y: float) -> float:
    """Computes exact Continuous Ranked Probability Score (CRPS)."""
    if pred_std <= 1e-6:
        return abs(actual_y - pred_mean)
    z = (actual_y - pred_mean) / pred_std
    phi_z = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    Phi_z = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return max(0.0, pred_std * (z * (2.0 * Phi_z - 1.0) + 2.0 * phi_z - 1.0 / math.sqrt(math.pi)))


def main():
    print("=== LOADING HOLDOUT DATASET (2020-2024) ===")
    
    # 1. Load Pre-Match Snapshots
    snap_ds = ds.dataset("data/datalake/rating_store_v4/pre_match_snapshots", partitioning="hive")
    snap_df = snap_ds.to_table().to_pandas()
    snap_df["date"] = pd.to_datetime(snap_df["match_date"])
    holdout_snaps = snap_df[(snap_df["date"] >= "2020-01-01") & (snap_df["date"] <= "2024-12-31")].copy()

    # 2. Load Player Match Actual Outcomes
    pm_ds = ds.dataset("data/datalake/feature_store_v3b/player_match", partitioning="hive")
    pm_df = pm_ds.to_table(columns=[
        "match_id", "player_id", "start_date", "match_format",
        "runs_scored", "balls_faced", "is_dismissed",
        "legal_balls_bowled", "runs_conceded", "wickets_credited"
    ]).to_pandas()

    # 3. Load Rolling Match (BM-1) and Rolling Time (BM-2) features
    rm_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_match", partitioning="hive")
    rm_df = rm_ds.to_table(columns=[
        "match_id", "player_id", "rolling_batting_sr", "rolling_economy_rate", "matches_in_window"
    ]).to_pandas()

    rt_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_time", partitioning="hive")
    rt_df = rt_ds.to_table(columns=[
        "match_id", "player_id", "decayed_batting_sr", "decayed_economy_rate"
    ]).to_pandas()

    # Merge all sources
    df = pd.merge(holdout_snaps, pm_df, on=["match_id", "player_id"], suffixes=("", "_pm"))
    df = pd.merge(df, rm_df, on=["match_id", "player_id"], how="left")
    df = pd.merge(df, rt_df, on=["match_id", "player_id"], how="left")

    print(f"Total merged holdout evaluation records: {len(df):,}")

    # =========================================================================
    # PART 1: BATTING PREDICTIVE EVALUATION (on players who faced balls)
    # =========================================================================
    bat_df = df[df["balls_faced"].fillna(0) > 0].copy()
    bat_df["actual_runs"] = bat_df["runs_scored"].astype(float)
    bat_df["b_faced"] = bat_df["balls_faced"].astype(float)
    
    # Baselines:
    # Format baseline strike rates
    format_base_sr = {"T20": 135.0, "ODI": 88.0, "TEST": 53.0}
    
    # BM-0: Population Mean
    bat_df["bm0_pred_runs"] = bat_df.apply(lambda r: r["b_faced"] * (format_base_sr.get(r["match_format"], 100.0) / 100.0), axis=1)
    
    # BM-1: Historical Rolling Mean (or fallback to BM-0 if missing)
    bat_df["bm1_pred_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (r["rolling_batting_sr"] / 100.0) if pd.notna(r["rolling_batting_sr"]) and r["rolling_batting_sr"] > 0
        else r["bm0_pred_runs"], axis=1
    )
    
    # BM-2: Recency-Weighted EWMA (or fallback to BM-1 / BM-0)
    bat_df["bm2_pred_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (r["decayed_batting_sr"] / 100.0) if pd.notna(r["decayed_batting_sr"]) and r["decayed_batting_sr"] > 0
        else r["bm1_pred_runs"], axis=1
    )
    
    # CA-HBSS: Model Prediction
    # theta_bat_rate = (pre_r_bat - 1000) / (350 * 0.65)
    # pred_runs = b_faced * base_sr * exp(theta_bat_rate)
    bat_df["cahbss_theta"] = (bat_df["pre_r_bat"] - 1000.0) / (350.0 * 0.65)
    bat_df["cahbss_pred_runs"] = bat_df.apply(
        lambda r: r["b_faced"] * (format_base_sr.get(r["match_format"], 100.0) / 100.0) * math.exp(max(-1.5, min(1.5, r["cahbss_theta"]))), axis=1
    )
    # Model predictive std ~ sqrt(phi * pred_runs^2 + pred_runs) + rd uncertainty
    bat_df["cahbss_pred_std"] = bat_df.apply(
        lambda r: math.sqrt(0.25 * (r["cahbss_pred_runs"]**2) + r["cahbss_pred_runs"] + 1.0) + (r["pre_rd_bat"] / 350.0) * 5.0, axis=1
    )

    print("\n" + "=" * 70)
    print("BATTING OUT-OF-SAMPLE PREDICTIVE EVALUATION (N = %d)" % len(bat_df))
    print("=" * 70)
    
    models = [
        ("BM-0: Population Average", "bm0_pred_runs"),
        ("BM-1: Rolling Average (M10)", "bm1_pred_runs"),
        ("BM-2: Recency-Weighted EWMA", "bm2_pred_runs"),
        ("CA-HBSS Rating Engine", "cahbss_pred_runs"),
    ]
    
    bat_results = []
    for name, col in models:
        err = bat_df["actual_runs"] - bat_df[col]
        mae = np.mean(np.abs(err))
        rmse = math.sqrt(np.mean(err**2))
        
        # Approximate CRPS
        std_col = bat_df["cahbss_pred_std"] if "cahbss" in col else pd.Series(15.0, index=bat_df.index)
        crps = np.mean([compute_crps_point(p, s, a) for p, s, a in zip(bat_df[col], std_col, bat_df["actual_runs"])])
        
        bat_results.append({
            "Model": name,
            "MAE (Runs)": round(mae, 2),
            "RMSE (Runs)": round(rmse, 2),
            "CRPS": round(crps, 2),
        })
    print(pd.DataFrame(bat_results).to_string(index=False))

    # 90% Interval Coverage for CA-HBSS Batting
    bat_df["low_90"] = bat_df["cahbss_pred_runs"] - 1.645 * bat_df["cahbss_pred_std"]
    bat_df["high_90"] = bat_df["cahbss_pred_runs"] + 1.645 * bat_df["cahbss_pred_std"]
    bat_coverage = np.mean((bat_df["actual_runs"] >= bat_df["low_90"]) & (bat_df["actual_runs"] <= bat_df["high_90"]))
    print(f"\nCA-HBSS Batting 90% Interval Empirical Coverage: {bat_coverage*100:.2f}% (Nominal: 90.0%)")

    # =========================================================================
    # PART 2: BOWLING PREDICTIVE EVALUATION (on players who bowled)
    # =========================================================================
    bowl_df = df[df["legal_balls_bowled"].fillna(0) > 0].copy()
    bowl_df["actual_wkts"] = bowl_df["wickets_credited"].astype(float)
    bowl_df["actual_runs_conceded"] = bowl_df["runs_conceded"].astype(float)
    bowl_df["balls_bowled"] = bowl_df["legal_balls_bowled"].astype(float)
    
    format_base_econ = {"T20": 8.10, "ODI": 5.25, "TEST": 3.15}
    format_base_haz = {"T20": 0.048, "ODI": 0.032, "TEST": 0.019}

    # BM-0: Population Mean
    bowl_df["bm0_pred_wkts"] = bowl_df.apply(lambda r: r["balls_bowled"] * format_base_haz.get(r["match_format"], 0.035), axis=1)
    bowl_df["bm0_pred_econ_runs"] = bowl_df.apply(lambda r: r["balls_bowled"] * (format_base_econ.get(r["match_format"], 6.0) / 6.0), axis=1)

    # BM-1: Rolling Average
    bowl_df["bm1_pred_econ_runs"] = bowl_df.apply(
        lambda r: r["balls_bowled"] * (r["rolling_economy_rate"] / 6.0) if pd.notna(r["rolling_economy_rate"]) and r["rolling_economy_rate"] > 0
        else r["bm0_pred_econ_runs"], axis=1
    )
    bowl_df["bm1_pred_wkts"] = bowl_df["bm0_pred_wkts"]  # fallback

    # BM-2: Decayed EWMA
    bowl_df["bm2_pred_econ_runs"] = bowl_df.apply(
        lambda r: r["balls_bowled"] * (r["decayed_economy_rate"] / 6.0) if pd.notna(r["decayed_economy_rate"]) and r["decayed_economy_rate"] > 0
        else r["bm1_pred_econ_runs"], axis=1
    )

    # CA-HBSS Prediction
    # theta_bowl_econ = -(pre_r_bowl - 1000) / (350 * 0.50)
    # theta_bowl_haz = (pre_r_bowl - 1000) / (350 * 0.50)
    bowl_df["cahbss_haz_z"] = (bowl_df["pre_r_bowl"] - 1000.0) / (350.0 * 0.50)
    bowl_df["cahbss_pred_wkts"] = bowl_df.apply(
        lambda r: r["balls_bowled"] * format_base_haz.get(r["match_format"], 0.035) * math.exp(max(-1.0, min(1.0, r["cahbss_haz_z"] * 0.3))), axis=1
    )
    bowl_df["cahbss_pred_econ_runs"] = bowl_df.apply(
        lambda r: r["balls_bowled"] * (format_base_econ.get(r["match_format"], 6.0) / 6.0) * math.exp(max(-1.0, min(1.0, -r["cahbss_haz_z"] * 0.2))), axis=1
    )
    bowl_df["cahbss_wkt_std"] = np.sqrt(bowl_df["cahbss_pred_wkts"] + 0.20 * (bowl_df["cahbss_pred_wkts"]**2))

    print("\n" + "=" * 70)
    print("BOWLING OUT-OF-SAMPLE PREDICTIVE EVALUATION (N = %d)" % len(bowl_df))
    print("=" * 70)

    bowl_wkt_results = []
    bowl_models = [
        ("BM-0: Population Average", "bm0_pred_wkts"),
        ("BM-1: Rolling Average", "bm1_pred_wkts"),
        ("CA-HBSS Rating Engine", "cahbss_pred_wkts"),
    ]
    for name, col in bowl_models:
        err = bowl_df["actual_wkts"] - bowl_df[col]
        mae = np.mean(np.abs(err))
        rmse = math.sqrt(np.mean(err**2))
        crps = np.mean([compute_crps_point(p, s, a) for p, s, a in zip(bowl_df[col], bowl_df["cahbss_wkt_std"], bowl_df["actual_wkts"])])
        bowl_wkt_results.append({
            "Model (Wickets)": name,
            "MAE (Wkts)": round(mae, 3),
            "RMSE (Wkts)": round(rmse, 3),
            "CRPS": round(crps, 3),
        })
    print(pd.DataFrame(bowl_wkt_results).to_string(index=False))

    # Economy Runs Conceded
    print("\nBOWLING RUNS CONCEDED:")
    bowl_econ_results = []
    econ_models = [
        ("BM-0: Population Average", "bm0_pred_econ_runs"),
        ("BM-1: Rolling Average", "bm1_pred_econ_runs"),
        ("BM-2: Recency-Weighted EWMA", "bm2_pred_econ_runs"),
        ("CA-HBSS Rating Engine", "cahbss_pred_econ_runs"),
    ]
    for name, col in econ_models:
        err = bowl_df["actual_runs_conceded"] - bowl_df[col]
        mae = np.mean(np.abs(err))
        rmse = math.sqrt(np.mean(err**2))
        bowl_econ_results.append({
            "Model (Runs Conceded)": name,
            "MAE (Runs)": round(mae, 2),
            "RMSE (Runs)": round(rmse, 2),
        })
    print(pd.DataFrame(bowl_econ_results).to_string(index=False))

    # 90% Interval Coverage for Bowling Wickets
    bowl_df["low_90_wkt"] = np.maximum(0.0, bowl_df["cahbss_pred_wkts"] - 1.645 * bowl_df["cahbss_wkt_std"])
    bowl_df["high_90_wkt"] = bowl_df["cahbss_pred_wkts"] + 1.645 * bowl_df["cahbss_wkt_std"]
    bowl_coverage = np.mean((bowl_df["actual_wkts"] >= bowl_df["low_90_wkt"]) & (bowl_df["actual_wkts"] <= bowl_df["high_90_wkt"]))
    print(f"\nCA-HBSS Bowling Wickets 90% Interval Empirical Coverage: {bowl_coverage*100:.2f}% (Nominal: 90.0%)")

    # =========================================================================
    # PART 3: RESULTS BY PLAYER EXPERIENCE LEVEL
    # =========================================================================
    print("\n" + "=" * 70)
    print("PREDICTIVE ACCURACY BY PLAYER EXPERIENCE LEVEL (CA-HBSS)")
    print("=" * 70)

    # Segment by matches_in_window
    bat_df["exp_tier"] = pd.cut(
        bat_df["matches_in_window"].fillna(0),
        bins=[-1, 4, 9, 999],
        labels=["Debutant (N<5)", "Moderate (5<=N<10)", "Established (N>=10)"]
    )
    
    tier_results = []
    for tier, grp in bat_df.groupby("exp_tier", observed=False):
        err = grp["actual_runs"] - grp["cahbss_pred_runs"]
        mae = np.mean(np.abs(err))
        rmse = math.sqrt(np.mean(err**2))
        avg_rd = grp["pre_rd_bat"].mean()
        tier_results.append({
            "Experience Tier": tier,
            "Count": len(grp),
            "Mean RD (Uncertainty)": round(avg_rd, 1),
            "MAE (Runs)": round(mae, 2),
            "RMSE (Runs)": round(rmse, 2),
        })
    print(pd.DataFrame(tier_results).to_string(index=False))


if __name__ == "__main__":
    main()
