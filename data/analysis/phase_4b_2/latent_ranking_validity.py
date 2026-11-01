"""
Phase 4B.2 Workstream D: Latent Rating Predictive Information Script.
Tests whether pre-match CA-HBSS ratings predict future performance rankings
beyond historical averages, using rank correlations (Spearman, Kendall),
player-clustered bootstrap confidence intervals, decile separation, experience stratification,
and ranking stability.
"""

import json
import os
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUTPUT_DIR = "data/analysis/phase_4b_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def compute_spearman(x, y):
    """Computes Spearman rank correlation using pandas ranks."""
    s_x = pd.Series(x)
    s_y = pd.Series(y)
    valid = s_x.notna() & s_y.notna()
    if valid.sum() < 5:
        return np.nan
    rx = s_x[valid].rank()
    ry = s_y[valid].rank()
    return float(rx.corr(ry))


def compute_kendall_approx(x, y, max_n=2000):
    """Computes Kendall tau rank correlation."""
    s_x = pd.Series(x)
    s_y = pd.Series(y)
    valid = s_x.notna() & s_y.notna()
    if valid.sum() < 5:
        return np.nan
    x_v = np.asarray(s_x[valid].values, dtype=float)
    y_v = np.asarray(s_y[valid].values, dtype=float)
    if len(x_v) > max_n:
        idx = np.random.default_rng(42).choice(len(x_v), size=max_n, replace=False)
        x_v, y_v = x_v[idx], y_v[idx]
    
    n = len(x_v)
    dx = x_v[:, None] - x_v[None, :]
    dy = y_v[:, None] - y_v[None, :]
    
    concordant = np.sum((dx > 0) & (dy > 0)) + np.sum((dx < 0) & (dy < 0))
    discordant = np.sum((dx > 0) & (dy < 0)) + np.sum((dx < 0) & (dy > 0))
    total_pairs = n * (n - 1)
    if total_pairs == 0:
        return np.nan
    return float((concordant - discordant) / total_pairs)


def clustered_bootstrap_spearman(df, cluster_col, pred_col, actual_col, n_boot=200, seed=42):
    """Computes player-clustered bootstrap 95% confidence intervals for Spearman rho."""
    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].unique()
    n_clusters = len(clusters)
    
    valid = df.dropna(subset=[pred_col, actual_col])
    if len(valid) < 10:
        return np.nan, (np.nan, np.nan)
    
    point_rho = compute_spearman(valid[pred_col], valid[actual_col])
    cluster_indices = df.groupby(cluster_col).indices
    
    boot_rhos = []
    for _ in range(n_boot):
        sample_clusters = rng.choice(clusters, size=n_clusters, replace=True)
        sample_idx = np.concatenate([cluster_indices[c] for c in sample_clusters])
        sample_df = df.iloc[sample_idx]
        r = compute_spearman(sample_df[pred_col], sample_df[actual_col])
        if not np.isnan(r):
            boot_rhos.append(r)
                
    if len(boot_rhos) > 20:
        ci_low = float(np.percentile(boot_rhos, 2.5))
        ci_high = float(np.percentile(boot_rhos, 97.5))
    else:
        ci_low, ci_high = np.nan, np.nan
        
    return float(point_rho), (round(ci_low, 3), round(ci_high, 3))


def main():
    print("=== WORKSTREAM D: LATENT RATING PREDICTIVE INFORMATION ===")

    # 1. Load holdout snapshots and player_match (unique 1-to-1)
    snap_ds = ds.dataset("data/datalake/rating_store_v4/pre_match_snapshots", partitioning="hive")
    snap_df = snap_ds.to_table().to_pandas()
    snap_df["date"] = pd.to_datetime(snap_df["match_date"])
    holdout_snaps = snap_df[(snap_df["date"] >= "2020-01-01") & (snap_df["date"] <= "2024-12-31")].copy()

    pm_ds = ds.dataset("data/datalake/feature_store_v3b/player_match", partitioning="hive")
    pm_df = pm_ds.to_table(columns=[
        "match_id", "player_id", "start_date", "match_format",
        "runs_scored", "balls_faced", "legal_balls_bowled", "runs_conceded", "wickets_credited"
    ]).to_pandas()

    rm_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_match", partitioning="hive")
    rm_df = rm_ds.to_table(
        filter=ds.field("window_size") == 10,
        columns=["match_id", "player_id", "rolling_batting_sr", "rolling_economy_rate", "matches_in_window"]
    ).to_pandas()

    rt_ds = ds.dataset("data/datalake/feature_store_v3b/rolling_time", partitioning="hive")
    rt_df = rt_ds.to_table(
        filter=ds.field("window_days") == 365,
        columns=["match_id", "player_id", "decayed_batting_sr", "decayed_economy_rate"]
    ).to_pandas()

    all_pm = pm_ds.to_table(columns=["match_id", "player_id", "start_date", "match_format"]).to_pandas()
    all_pm["start_date"] = pd.to_datetime(all_pm["start_date"])
    all_pm = all_pm.sort_values(["player_id", "start_date", "match_id"])
    all_pm["format_matches_prior"] = all_pm.groupby(["player_id", "match_format"]).cumcount()
    prior_counts = all_pm[["match_id", "player_id", "format_matches_prior"]]

    df = pd.merge(holdout_snaps, pm_df, on=["match_id", "player_id"], suffixes=("", "_pm"))
    df = pd.merge(df, rm_df, on=["match_id", "player_id"], how="left")
    df = pd.merge(df, rt_df, on=["match_id", "player_id"], how="left")
    df = pd.merge(df, prior_counts, on=["match_id", "player_id"], how="left")
    df["exp_tier"] = pd.cut(
        df["format_matches_prior"].fillna(0),
        bins=[-1, 4, 9, 9999],
        labels=["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]
    )

    # =========================================================================
    # TEST 1: RANK CORRELATIONS (BATTERY OF PREDICTORS VS SUBSEQUENT MATCH OUTCOMES)
    # =========================================================================
    # Batting:
    bat_df = df[df["balls_faced"].fillna(0) > 0].copy()
    bat_df["match_bat_sr"] = (bat_df["runs_scored"] / bat_df["balls_faced"]) * 100.0
    bat_df["match_runs"] = bat_df["runs_scored"].astype(float)

    print("\n--- TEST 1: BATTING RANK CORRELATION WITH SUBSEQUENT MATCH PERFORMANCE ---")
    bat_rank_results = []
    for pred_name, col in [("CA-HBSS pre_r_bat", "pre_r_bat"), ("BM-1 rolling_batting_sr", "rolling_batting_sr"), ("BM-2 decayed_batting_sr", "decayed_batting_sr")]:
        # Vs Match Runs
        rho, ci = clustered_bootstrap_spearman(bat_df, "player_id", col, "match_runs")
        tau = compute_kendall_approx(bat_df[col], bat_df["match_runs"])
        bat_rank_results.append({
            "Predictor": pred_name,
            "Target": "Match Runs Scored",
            "Spearman Rho": round(rho, 3),
            "Clustered 95% CI": str(ci),
            "Kendall Tau": round(tau, 3)
        })
        # Vs Match Strike Rate
        rho_sr, ci_sr = clustered_bootstrap_spearman(bat_df, "player_id", col, "match_bat_sr")
        tau_sr = compute_kendall_approx(bat_df[col], bat_df["match_bat_sr"])
        bat_rank_results.append({
            "Predictor": pred_name,
            "Target": "Match Strike Rate",
            "Spearman Rho": round(rho_sr, 3),
            "Clustered 95% CI": str(ci_sr),
            "Kendall Tau": round(tau_sr, 3)
        })
    print(pd.DataFrame(bat_rank_results).to_string(index=False))

    # Bowling:
    bowl_df = df[df["legal_balls_bowled"].fillna(0) > 0].copy()
    bowl_df["match_econ"] = (bowl_df["runs_conceded"] / (bowl_df["legal_balls_bowled"] / 6.0))
    bowl_df["match_wkts"] = bowl_df["wickets_credited"].astype(float)

    print("\n--- TEST 1: BOWLING RANK CORRELATION WITH SUBSEQUENT MATCH PERFORMANCE ---")
    bowl_rank_results = []
    for pred_name, col in [("CA-HBSS pre_r_bowl", "pre_r_bowl"), ("BM-1 rolling_economy", "rolling_economy_rate"), ("BM-2 decayed_economy", "decayed_economy_rate")]:
        # Vs Match Wickets
        rho_wkt, ci_wkt = clustered_bootstrap_spearman(bowl_df, "player_id", col, "match_wkts")
        tau_wkt = compute_kendall_approx(bowl_df[col], bowl_df["match_wkts"])
        bowl_rank_results.append({
            "Predictor": pred_name,
            "Target": "Match Wickets",
            "Spearman Rho": round(rho_wkt, 3),
            "Clustered 95% CI": str(ci_wkt),
            "Kendall Tau": round(tau_wkt, 3)
        })
        # Vs Match Economy (Note: for economy, lower is better, so pre_r_bowl should negatively correlate with economy)
        rho_ec, ci_ec = clustered_bootstrap_spearman(bowl_df, "player_id", col, "match_econ")
        tau_ec = compute_kendall_approx(bowl_df[col], bowl_df["match_econ"])
        bowl_rank_results.append({
            "Predictor": pred_name,
            "Target": "Match Economy Rate",
            "Spearman Rho": round(rho_ec, 3),
            "Clustered 95% CI": str(ci_ec),
            "Kendall Tau": round(tau_ec, 3)
        })
    print(pd.DataFrame(bowl_rank_results).to_string(index=False))

    # =========================================================================
    # TEST 2: DECILE SEPARATION ON SUBSEQUENT MATCH PERFORMANCE
    # =========================================================================
    print("\n--- TEST 2: DECILE SEPARATION (CA-HBSS PRE-MATCH RATINGS) ---")
    # Batting deciles
    bat_df["rating_decile"] = pd.qcut(bat_df["pre_r_bat"], q=10, labels=[f"D{i+1}" for i in range(10)])
    bat_dec_summary = bat_df.groupby("rating_decile", observed=False).agg(
        n=("match_runs", "count"),
        mean_rating=("pre_r_bat", "mean"),
        mean_runs=("match_runs", "mean"),
        median_runs=("match_runs", "median"),
        mean_sr=("match_bat_sr", "mean"),
        p75_runs=("match_runs", lambda s: np.percentile(s, 75))
    ).reset_index()
    print("\nBATTING DECILE SEPARATION:")
    print(bat_dec_summary.to_string(index=False))

    # Bowling deciles
    bowl_df["rating_decile"] = pd.qcut(bowl_df["pre_r_bowl"], q=10, labels=[f"D{i+1}" for i in range(10)])
    bowl_dec_summary = bowl_df.groupby("rating_decile", observed=False).agg(
        n=("match_wkts", "count"),
        mean_rating=("pre_r_bowl", "mean"),
        mean_wkts=("match_wkts", "mean"),
        mean_econ=("match_econ", "mean"),
        pct_multi_wkt=("match_wkts", lambda s: np.mean(s >= 2) * 100.0)
    ).reset_index()
    print("\nBOWLING DECILE SEPARATION:")
    print(bowl_dec_summary.to_string(index=False))

    # =========================================================================
    # TEST 3: EXPERIENCE STRATIFICATION
    # =========================================================================
    print("\n--- TEST 3: RANK CORRELATION BY EXPERIENCE TIER ---")
    tier_rank_results = []
    for tier in ["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]:
        b_sub = bat_df[bat_df["exp_tier"] == tier]
        rho_bat, ci_bat = clustered_bootstrap_spearman(b_sub, "player_id", "pre_r_bat", "match_runs")
        rho_bm1, ci_bm1 = clustered_bootstrap_spearman(b_sub, "player_id", "rolling_batting_sr", "match_runs")
        tier_rank_results.append({
            "Tier": tier,
            "Discipline": "Batting Runs",
            "N": len(b_sub),
            "CA-HBSS Rho": round(rho_bat, 3),
            "CA-HBSS 95% CI": str(ci_bat),
            "BM-1 Rho": round(rho_bm1, 3),
            "BM-1 95% CI": str(ci_bm1),
        })
        bw_sub = bowl_df[bowl_df["exp_tier"] == tier]
        rho_bw, ci_bw = clustered_bootstrap_spearman(bw_sub, "player_id", "pre_r_bowl", "match_wkts")
        rho_bm1_bw, ci_bm1_bw = clustered_bootstrap_spearman(bw_sub, "player_id", "rolling_economy_rate", "match_wkts")
        tier_rank_results.append({
            "Tier": tier,
            "Discipline": "Bowling Wickets",
            "N": len(bw_sub),
            "CA-HBSS Rho": round(rho_bw, 3),
            "CA-HBSS 95% CI": str(ci_bw),
            "BM-1 Rho": round(rho_bm1_bw, 3),
            "BM-1 95% CI": str(ci_bm1_bw),
        })
    print(pd.DataFrame(tier_rank_results).to_string(index=False))

    # =========================================================================
    # TEST 4: YEAR-TO-YEAR RANKING STABILITY & TOP-DECILE RETENTION
    # =========================================================================
    print("\n--- TEST 4: YEAR-TO-YEAR RANKING STABILITY ---")
    chk_ds = ds.dataset("data/datalake/rating_store_v4/player_rating_history", partitioning="hive")
    chk_df = chk_ds.to_table().to_pandas()
    chk_df["year"] = pd.to_numeric(chk_df["year"])
    
    # Analyze annual stability in T20 from 2020 to 2024
    t20_chk = chk_df[chk_df["match_format"].str.upper() == "T20"].copy()
    stability_records = []
    for y in range(2020, 2024):
        y1 = t20_chk[t20_chk["year"] == y].dropna(subset=["r_bat", "r_bowl"])
        y2 = t20_chk[t20_chk["year"] == y+1].dropna(subset=["r_bat", "r_bowl"])
        paired = pd.merge(y1, y2, on="player_id", suffixes=("_t1", "_t2"))
        
        rho_bat_stab = compute_spearman(paired["r_bat_t1"], paired["r_bat_t2"])
        rho_bowl_stab = compute_spearman(paired["r_bowl_t1"], paired["r_bowl_t2"])
        
        # Top decile retention (batting)
        top_dec_t1 = set(paired.nlargest(int(len(paired) * 0.1), "r_bat_t1")["player_id"])
        top_dec_t2 = set(paired.nlargest(int(len(paired) * 0.1), "r_bat_t2")["player_id"])
        retention = len(top_dec_t1 & top_dec_t2) / max(1, len(top_dec_t1))
        
        stability_records.append({
            "Transition": f"{y} -> {y+1}",
            "Paired Players": len(paired),
            "Batting Rank Autocorrelation": round(rho_bat_stab, 3),
            "Bowling Rank Autocorrelation": round(rho_bowl_stab, 3),
            "Top-Decile Retention Rate": f"{retention*100:.1f}%"
        })
    print(pd.DataFrame(stability_records).to_string(index=False))

    # Save outputs
    out = {
        "batting_rank_correlations": bat_rank_results,
        "bowling_rank_correlations": bowl_rank_results,
        "batting_decile_separation": bat_dec_summary.to_dict(orient="records"),
        "bowling_decile_separation": bowl_dec_summary.to_dict(orient="records"),
        "tier_stratification": tier_rank_results,
        "stability_records": stability_records
    }
    with open(os.path.join(OUTPUT_DIR, "latent_ranking_results.json"), "w") as f:
        json.dump(out, f, indent=2)

    pd.DataFrame(bat_rank_results).to_csv(os.path.join(OUTPUT_DIR, "batting_rank_correlations.csv"), index=False)
    pd.DataFrame(bowl_rank_results).to_csv(os.path.join(OUTPUT_DIR, "bowling_rank_correlations.csv"), index=False)
    bat_dec_summary.to_csv(os.path.join(OUTPUT_DIR, "batting_decile_separation.csv"), index=False)
    bowl_dec_summary.to_csv(os.path.join(OUTPUT_DIR, "bowling_decile_separation.csv"), index=False)
    pd.DataFrame(stability_records).to_csv(os.path.join(OUTPUT_DIR, "ranking_stability.csv"), index=False)
    print(f"\nSaved all ranking validity artifacts to {OUTPUT_DIR}/latent_ranking_results.json and CSVs.")


if __name__ == "__main__":
    main()
