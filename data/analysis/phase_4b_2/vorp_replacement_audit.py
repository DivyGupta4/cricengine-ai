"""
Phase 4B.2 Workstream E: VORP Replacement Level Audit Script.
Empirically evaluates candidate replacement level definitions across formats,
disciplines, and inferred roles on player_rating_current.
Tests candidate thresholds (P05, P10, P25, fringe N<5, and the proposed 650/900),
evaluating surplus balance, negative VORP percentages, and all-rounder impact.
"""

import json
import os
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

OUTPUT_DIR = "data/analysis/phase_4b_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def compute_vorp_candidate(df, r_rep_bat, r_rep_bowl, r_rep_field=650.0):
    """Computes VORP using custom discipline replacement thresholds."""
    # Role weights
    weights = {
        "BATTER": {"w_bat": 0.85, "w_bowl": 0.05, "w_fld": 0.10},
        "BOWLER": {"w_bat": 0.05, "w_bowl": 0.85, "w_fld": 0.10},
        "ALL_ROUNDER": {"w_bat": 0.45, "w_bowl": 0.45, "w_fld": 0.10},
        "WICKETKEEPER": {"w_bat": 0.80, "w_bowl": 0.00, "w_fld": 0.20},
    }
    
    def get_vorp(r):
        role = r["inferred_role"]
        w = weights.get(role, {"w_bat": 0.33, "w_bowl": 0.33, "w_fld": 0.34})
        surplus_bat = (r["r_bat"] - r_rep_bat) / 100.0
        surplus_bowl = (r["r_bowl"] - r_rep_bowl) / 100.0
        surplus_fld = (r["r_field"] - r_rep_field) / 100.0
        return w["w_bat"] * surplus_bat + w["w_bowl"] * surplus_bowl + w["w_fld"] * surplus_fld

    return df.apply(get_vorp, axis=1)


def main():
    print("=== WORKSTREAM E: VORP REPLACEMENT LEVEL AUDIT ===")

    # 1. Load current ratings dataset
    curr_ds = ds.dataset("data/datalake/rating_store_v4/player_rating_current", partitioning="hive")
    curr_df = curr_ds.to_table().to_pandas()
    print(f"Total current rating states: {len(curr_df):,}")

    formats = ["T20", "ODI", "TEST"]
    disciplines = ["r_bat", "r_bowl", "r_field"]

    # 2. Empirical Distribution Percentiles by Format and Discipline
    dist_metrics = []
    for fmt in formats:
        f_df = curr_df[curr_df["match_format"].str.upper() == fmt]
        active_f = f_df[f_df["rating_status"] == "ACTIVE"]
        fringe_f = f_df[f_df["observations_count"] < 5]
        
        for d in disciplines:
            s_all = f_df[d]
            s_act = active_f[d]
            s_frg = fringe_f[d]
            
            dist_metrics.append({
                "Format": fmt,
                "Discipline": d,
                "All Mean": round(s_all.mean(), 1),
                "All P05": round(s_all.quantile(0.05), 1),
                "All P10": round(s_all.quantile(0.10), 1),
                "All P25": round(s_all.quantile(0.25), 1),
                "Active Mean": round(s_act.mean(), 1),
                "Active P05": round(s_act.quantile(0.05), 1),
                "Active P10": round(s_act.quantile(0.10), 1),
                "Active P25": round(s_act.quantile(0.25), 1),
                "Fringe Mean (N<5)": round(s_frg.mean(), 1),
                "Fringe P10 (N<5)": round(s_frg.quantile(0.10), 1),
            })
    print("\n--- EMPIRICAL RATING DISTRIBUTION PERCENTILES ---")
    dist_df = pd.DataFrame(dist_metrics)
    print(dist_df.to_string(index=False))

    # 3. Candidate Replacement Level Definitions
    # Let's test 5 candidate definitions:
    # Candidate 1: Current Baseline (Uniform 650 / 650)
    # Candidate 2: Proposed 4B.1 Hypothesis (Bat 650 / Bowl 900)
    # Candidate 3: Active P05 (Format-specific bottom 5th percentile of active players)
    # Candidate 4: Active P10 (Format-specific bottom decile of active players)
    # Candidate 5: Active P25 (Format-specific bottom quartile of active players)
    
    candidate_evaluations = []

    for fmt in formats:
        f_df = curr_df[curr_df["match_format"].str.upper() == fmt].copy()
        act_f = f_df[f_df["rating_status"] == "ACTIVE"]
        
        candidates = {
            "C1_Current_Uniform_650": {
                "r_bat": 650.0,
                "r_bowl": 650.0,
                "r_fld": 650.0,
                "desc": "Uniform 650 across all disciplines"
            },
            "C2_Proposed_Hypothesis_650_900": {
                "r_bat": 650.0,
                "r_bowl": 900.0,
                "r_fld": 650.0,
                "desc": "Heuristic 650 Batting / 900 Bowling"
            },
            "C3_Active_P05": {
                "r_bat": round(act_f["r_bat"].quantile(0.05), 1),
                "r_bowl": round(act_f["r_bowl"].quantile(0.05), 1),
                "r_fld": round(act_f["r_field"].quantile(0.05), 1),
                "desc": "Empirical 5th percentile of active players"
            },
            "C4_Active_P10_Decile": {
                "r_bat": round(act_f["r_bat"].quantile(0.10), 1),
                "r_bowl": round(act_f["r_bowl"].quantile(0.10), 1),
                "r_fld": round(act_f["r_field"].quantile(0.10), 1),
                "desc": "Empirical 10th percentile (bottom decile) of active players"
            },
            "C5_Active_P25_Quartile": {
                "r_bat": round(act_f["r_bat"].quantile(0.25), 1),
                "r_bowl": round(act_f["r_bowl"].quantile(0.25), 1),
                "r_fld": round(act_f["r_field"].quantile(0.25), 1),
                "desc": "Empirical 25th percentile (bottom quartile) of active players"
            }
        }

        # Calculate baseline VORP for rank correlation
        f_df["vorp_baseline"] = f_df["vorp_rating"]

        for c_name, c_spec in candidates.items():
            r_bat_thresh = c_spec["r_bat"]
            r_bowl_thresh = c_spec["r_bowl"]
            r_fld_thresh = c_spec["r_fld"]
            
            vorp_c = compute_vorp_candidate(f_df, r_bat_thresh, r_bowl_thresh, r_fld_thresh)
            f_df[f"vorp_{c_name}"] = vorp_c
            
            # Discipline surpluses
            surplus_bat = (f_df["r_bat"] - r_bat_thresh) / 100.0
            surplus_bowl = (f_df["r_bowl"] - r_bowl_thresh) / 100.0
            
            # All-rounder surplus balance (for all-rounders: R6 and R7)
            ar_df = f_df[f_df["inferred_role"].isin(["R6_PACE_ALLROUNDER", "R7_SPIN_ALLROUNDER"])]
            ar_surplus_bat = (ar_df["r_bat"] - r_bat_thresh) / 100.0
            ar_surplus_bowl = (ar_df["r_bowl"] - r_bowl_thresh) / 100.0
            
            # Batter surplus balance (R1, R2, R3, R4)
            bat_spec_df = f_df[f_df["inferred_role"].isin(["R1_OPENER", "R2_TOP_ORDER", "R3_MIDDLE_ORDER", "R4_FINISHER"])]
            
            # Bowler surplus balance (R8, R9)
            bowl_spec_df = f_df[f_df["inferred_role"].isin(["R8_PACE_SPECIALIST", "R9_SPIN_SPECIALIST"])]
            
            # Rank correlation with baseline
            rho = float(f_df["vorp_baseline"].rank().corr(vorp_c.rank()))
            pct_negative = float(np.mean(vorp_c < 0.0) * 100.0)

            candidate_evaluations.append({
                "Format": fmt,
                "Candidate": c_name,
                "Bat Threshold": r_bat_thresh,
                "Bowl Threshold": r_bowl_thresh,
                "Mean Surplus Bat": round(surplus_bat.mean(), 2),
                "Mean Surplus Bowl": round(surplus_bowl.mean(), 2),
                "Surplus Ratio (Bowl/Bat)": round(surplus_bowl.mean() / max(0.01, surplus_bat.mean()), 2),
                "AR Count": len(ar_df),
                "AR Mean Surplus Bat": round(ar_surplus_bat.mean(), 2) if len(ar_df) > 0 else np.nan,
                "AR Mean Surplus Bowl": round(ar_surplus_bowl.mean(), 2) if len(ar_df) > 0 else np.nan,
                "AR Surplus Ratio": round(ar_surplus_bowl.mean() / max(0.01, ar_surplus_bat.mean()), 2) if len(ar_df) > 0 else np.nan,
                "Mean VORP": round(vorp_c.mean(), 2),
                "Median VORP": round(vorp_c.median(), 2),
                "Min VORP": round(vorp_c.min(), 2),
                "Max VORP": round(vorp_c.max(), 2),
                "% Below Replacement": round(pct_negative, 2),
                "Spearman Rho vs Baseline": round(rho, 4)
            })

    print("\n--- CANDIDATE REPLACEMENT LEVEL EVALUATIONS ---")
    cand_df = pd.DataFrame(candidate_evaluations)
    print(cand_df.to_string(index=False))

    # Save artifacts
    dist_df.to_csv(os.path.join(OUTPUT_DIR, "vorp_distribution_percentiles.csv"), index=False)
    cand_df.to_csv(os.path.join(OUTPUT_DIR, "vorp_candidate_evaluations.csv"), index=False)
    
    with open(os.path.join(OUTPUT_DIR, "vorp_replacement_analysis.json"), "w") as f:
        json.dump({
            "distribution_percentiles": dist_metrics,
            "candidate_evaluations": candidate_evaluations
        }, f, indent=2)

    print(f"\nSaved VORP analysis artifacts to {OUTPUT_DIR}/vorp_replacement_analysis.json and CSVs.")


if __name__ == "__main__":
    main()
