"""
Phase 4B.2 Workstream C: Uncertainty Mathematics Audit Script.
Traces production implementation vs audit script approximations,
reconstructs the exact Law of Total Variance combining epistemic and aleatoric uncertainty,
and evaluates empirical coverage, interval width (sharpness), and Winkler Interval Scores
at 50%, 80%, 90%, and 95% nominal levels.
"""

import json
import math
import os
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUTPUT_DIR = "data/analysis/phase_4b_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def winkler_interval_score(l, u, y, alpha):
    """
    Computes the Winkler Interval Score (proper scoring rule for prediction intervals).
    IS_alpha = (u - l) + (2/alpha)*(l - y)*I(y < l) + (2/alpha)*(y - u)*I(y > u)
    Lower score indicates better performance (penalizes wide intervals and non-coverage).
    """
    width = u - l
    penalty = 0.0
    if y < l:
        penalty = (2.0 / alpha) * (l - y)
    elif y > u:
        penalty = (2.0 / alpha) * (y - u)
    return width + penalty


def evaluate_calibration_levels(df, pred_mean_col, pred_std_col, actual_col):
    """Evaluates coverage, sharpness, and interval scores at 50%, 80%, 90%, 95% nominal levels."""
    levels = [
        (0.50, 0.674),
        (0.80, 1.282),
        (0.90, 1.645),
        (0.95, 1.960)
    ]
    results = {}
    n = len(df)
    
    means = df[pred_mean_col].values
    stds = df[pred_std_col].values
    actuals = df[actual_col].values
    
    for nom, z in levels:
        alpha = 1.0 - nom
        low = np.maximum(0.0, means - z * stds)
        high = means + z * stds
        
        covered = (actuals >= low) & (actuals <= high)
        cov_rate = float(np.mean(covered))
        
        widths = high - low
        mean_width = float(np.mean(widths))
        median_width = float(np.median(widths))
        
        scores = [winkler_interval_score(l, u, y, alpha) for l, u, y in zip(low, high, actuals)]
        mean_score = float(np.mean(scores))
        
        results[f"{int(nom*100)}%"] = {
            "nominal_coverage": nom,
            "empirical_coverage": round(cov_rate, 4),
            "coverage_gap": round(cov_rate - nom, 4),
            "mean_width": round(mean_width, 2),
            "median_width": round(median_width, 2),
            "winkler_score": round(mean_score, 2)
        }
    return results


def main():
    print("=== WORKSTREAM C: UNCERTAINTY MATHEMATICS AUDIT ===")

    # 1. Load holdout snapshots and player_match (unique 1-to-1)
    snap_ds = ds.dataset("data/datalake/rating_store_v4/pre_match_snapshots", partitioning="hive")
    snap_df = snap_ds.to_table().to_pandas()
    snap_df["date"] = pd.to_datetime(snap_df["match_date"])
    holdout_snaps = snap_df[(snap_df["date"] >= "2020-01-01") & (snap_df["date"] <= "2024-12-31")].copy()

    pm_ds = ds.dataset("data/datalake/feature_store_v3b/player_match", partitioning="hive")
    pm_df = pm_ds.to_table(columns=[
        "match_id", "player_id", "start_date", "match_format",
        "runs_scored", "balls_faced", "legal_balls_bowled", "wickets_credited"
    ]).to_pandas()

    all_pm = pm_ds.to_table(columns=["match_id", "player_id", "start_date", "match_format"]).to_pandas()
    all_pm["start_date"] = pd.to_datetime(all_pm["start_date"])
    all_pm = all_pm.sort_values(["player_id", "start_date", "match_id"])
    all_pm["format_matches_prior"] = all_pm.groupby(["player_id", "match_format"]).cumcount()
    prior_counts = all_pm[["match_id", "player_id", "format_matches_prior"]]

    df = pd.merge(holdout_snaps, pm_df, on=["match_id", "player_id"], suffixes=("", "_pm"))
    df = pd.merge(df, prior_counts, on=["match_id", "player_id"], how="left")
    df["exp_tier"] = pd.cut(
        df["format_matches_prior"].fillna(0),
        bins=[-1, 4, 9, 9999],
        labels=["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]
    )

    format_base_sr = {"T20": 135.0, "ODI": 88.0, "TEST": 53.0}
    format_base_haz = {"T20": 0.035, "ODI": 0.030, "TEST": 0.028}

    # =========================================================================
    # PART 1: BATTING UNCERTAINTY
    # =========================================================================
    bat_df = df[df["balls_faced"].fillna(0) > 0].copy()
    bat_df["actual_runs"] = bat_df["runs_scored"].astype(float)
    bat_df["b_faced"] = bat_df["balls_faced"].astype(float)

    # Latent parameters
    bat_df["theta_bat"] = (bat_df["pre_r_bat"] - 1000.0) / 350.0
    bat_df["sigma_theta_bat"] = bat_df["pre_rd_bat"] / 350.0  # Epistemic standard deviation
    bat_df["var_theta_bat"] = bat_df["sigma_theta_bat"]**2     # Epistemic variance

    # Rate multiplier beta = 0.35 (Phase 4B.1 scaling)
    beta_bat = 0.35
    bat_df["lambda_base"] = bat_df.apply(
        lambda r: (format_base_sr.get(str(r["match_format"]).upper(), 100.0) / 100.0), axis=1
    )
    
    # Expected mean under lognormal transformation: E[exp(beta * theta)] = exp(beta*theta + 0.5*beta^2*sigma^2)
    bat_df["cahbss_pred_mean"] = bat_df.apply(
        lambda r: r["b_faced"] * r["lambda_base"] * math.exp(r["theta_bat"] * beta_bat + 0.5 * (beta_bat**2) * r["var_theta_bat"]), axis=1
    )

    # 1. Formula used in Phase 4B.1 script (Ad-Hoc Linear Combination):
    bat_df["std_adhoc_4b1"] = bat_df.apply(
        lambda r: math.sqrt(0.25 * (r["cahbss_pred_mean"]**2) + r["cahbss_pred_mean"] + 1.0) + (r["pre_rd_bat"] / 350.0) * 5.0, axis=1
    )

    # 2. Mathematically Rigorous Law of Total Variance Combination:
    # Var_total = E[Var(Y|theta)] + Var(E[Y|theta])
    # Aleatoric: Var(Y|theta) = mu + alpha * mu^2 (Negative Binomial overdispersion with alpha = 0.25)
    # Epistemic: Var(E[Y|theta]) = B^2 * lambda_base^2 * exp(2*beta*theta + beta^2*sigma^2) * (exp(beta^2*sigma^2) - 1)
    def compute_rigorous_total_std_bat(r, alpha=0.25):
        b = r["b_faced"]
        l_base = r["lambda_base"]
        th = r["theta_bat"]
        v_th = r["var_theta_bat"]
        
        # Expected count
        mu = b * l_base * math.exp(th * beta_bat + 0.5 * (beta_bat**2) * v_th)
        
        # Aleatoric component
        var_aleatoric = mu + alpha * (mu**2)
        
        # Epistemic component
        term1 = (b * l_base)**2 * math.exp(2.0 * beta_bat * th + (beta_bat**2) * v_th)
        term2 = math.exp((beta_bat**2) * v_th) - 1.0
        var_epistemic = term1 * term2
        
        var_total = var_aleatoric + var_epistemic
        return math.sqrt(max(0.1, var_total))

    bat_df["std_rigorous_total"] = bat_df.apply(compute_rigorous_total_std_bat, axis=1)

    print("\n--- BATTING UNCERTAINTY CALIBRATION (N = 4,951) ---")
    print("\n1. Ad-Hoc Phase 4B.1 Implementation:")
    adhoc_bat_cal = evaluate_calibration_levels(bat_df, "cahbss_pred_mean", "std_adhoc_4b1", "actual_runs")
    print(pd.DataFrame(adhoc_bat_cal).T)

    print("\n2. Rigorous Law of Total Variance Implementation:")
    rigorous_bat_cal = evaluate_calibration_levels(bat_df, "cahbss_pred_mean", "std_rigorous_total", "actual_runs")
    print(pd.DataFrame(rigorous_bat_cal).T)

    # By Experience Tier (Rigorous Formulation)
    bat_tier_cal = {}
    for tier in ["Debutant (<5)", "Moderate (5-9)", "Established (>=10)"]:
        sub = bat_df[bat_df["exp_tier"] == tier]
        bat_tier_cal[tier] = evaluate_calibration_levels(sub, "cahbss_pred_mean", "std_rigorous_total", "actual_runs")

    # =========================================================================
    # PART 2: BOWLING WICKETS UNCERTAINTY
    # =========================================================================
    bowl_df = df[df["legal_balls_bowled"].fillna(0) > 0].copy()
    bowl_df["actual_wkts"] = bowl_df["wickets_credited"].astype(float)
    bowl_df["b_bowled"] = bowl_df["legal_balls_bowled"].astype(float)

    beta_bowl = 0.30
    bowl_df["theta_bowl"] = (bowl_df["pre_r_bowl"] - 1000.0) / 350.0
    bowl_df["sigma_theta_bowl"] = bowl_df["pre_rd_bowl"] / 350.0
    bowl_df["var_theta_bowl"] = bowl_df["sigma_theta_bowl"]**2

    bowl_df["haz_base"] = bowl_df.apply(
        lambda r: format_base_haz.get(str(r["match_format"]).upper(), 0.032), axis=1
    )
    bowl_df["cahbss_pred_mean_wkts"] = bowl_df.apply(
        lambda r: r["b_bowled"] * r["haz_base"] * math.exp(r["theta_bowl"] * beta_bowl + 0.5 * (beta_bowl**2) * r["var_theta_bowl"]), axis=1
    )

    # 1. Phase 4B.1 Ad-Hoc formula (Zero Epistemic Uncertainty):
    bowl_df["std_adhoc_wkt"] = np.sqrt(bowl_df["cahbss_pred_mean_wkts"] + 0.20 * (bowl_df["cahbss_pred_mean_wkts"]**2))

    # 2. Rigorous Law of Total Variance Formulation:
    def compute_rigorous_total_std_bowl(r, alpha=0.20):
        b = r["b_bowled"]
        h_base = r["haz_base"]
        th = r["theta_bowl"]
        v_th = r["var_theta_bowl"]
        
        mu = b * h_base * math.exp(th * beta_bowl + 0.5 * (beta_bowl**2) * v_th)
        var_aleatoric = mu + alpha * (mu**2)
        
        term1 = (b * h_base)**2 * math.exp(2.0 * beta_bowl * th + (beta_bowl**2) * v_th)
        term2 = math.exp((beta_bowl**2) * v_th) - 1.0
        var_epistemic = term1 * term2
        
        return math.sqrt(max(0.01, var_aleatoric + var_epistemic))

    bowl_df["std_rigorous_wkt"] = bowl_df.apply(compute_rigorous_total_std_bowl, axis=1)

    print("\n--- BOWLING WICKETS UNCERTAINTY CALIBRATION (N = 3,599) ---")
    print("\n1. Ad-Hoc Phase 4B.1 Implementation (Aleatoric Only):")
    adhoc_bowl_cal = evaluate_calibration_levels(bowl_df, "cahbss_pred_mean_wkts", "std_adhoc_wkt", "actual_wkts")
    print(pd.DataFrame(adhoc_bowl_cal).T)

    print("\n2. Rigorous Law of Total Variance Implementation:")
    rigorous_bowl_cal = evaluate_calibration_levels(bowl_df, "cahbss_pred_mean_wkts", "std_rigorous_wkt", "actual_wkts")
    print(pd.DataFrame(rigorous_bowl_cal).T)

    # Save all calibration artifacts
    uncertainty_results = {
        "batting_adhoc_calibration": adhoc_bat_cal,
        "batting_rigorous_calibration": rigorous_bat_cal,
        "batting_by_tier_rigorous": bat_tier_cal,
        "bowling_adhoc_calibration": adhoc_bowl_cal,
        "bowling_rigorous_calibration": rigorous_bowl_cal
    }
    with open(os.path.join(OUTPUT_DIR, "uncertainty_calibration_results.json"), "w") as f:
        json.dump(uncertainty_results, f, indent=2)

    print(f"\nSaved uncertainty calibration results to {OUTPUT_DIR}/uncertainty_calibration_results.json")


if __name__ == "__main__":
    main()
