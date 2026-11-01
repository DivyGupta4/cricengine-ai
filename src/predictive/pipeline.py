"""
CricEngine AI — Integrated Predictive, Calibration & VORP Pipeline (Phase 4C)

Orchestrates:
1. End-to-end data extraction and D-1 temporal verification
2. Calibrated two-stage predictive modeling for batting, bowling, and fielding
3. Law of Total Variance integration and prediction interval generation (50%, 80%, 90%, 95%)
4. Benchmark comparison against BM-0, BM-1, BM-2, and BM-3
5. Statistical calibration assessment (coverage, reliability diagrams, mid-PIT)
6. Empirically grounded VORP materialization with active P10 baselines
7. Hive-partitioned Parquet storage and SHA-256 manifest generation
"""

from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Dict, Any, List, Optional, Tuple
import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.predictive.config import (
    BASE_DIR,
    CURATED_DB_PATH,
    FEATURE_STORE_V3B_DIR,
    RATING_STORE_V4_DIR,
    PREDICTIVE_STORE_V4C_DIR,
    ANALYSIS_DIR,
    DOCS_DIR,
    FORMATS,
    FORMAT_CONFIGS,
    PredictiveEngineConfig,
)
from src.predictive.uncertainty import (
    compute_total_variance,
    compute_prediction_intervals,
    compute_winkler_score,
    compute_discrete_crps,
)
from src.predictive.batting_model import predict_batting_performance
from src.predictive.bowling_model import predict_bowling_performance
from src.predictive.fielding_model import predict_fielding_performance
from src.predictive.allround_model import predict_allround_net_contribution
from src.predictive.vorp import calculate_player_vorp, compute_pool_surplus_ratio
from src.predictive.calibration import (
    evaluate_interval_coverage,
    compute_calibration_curve,
    compute_mid_pit,
)
from src.predictive.baselines import (
    compute_regression_metrics,
    compute_spearman_rho,
    compute_kendall_tau,
)
from src.predictive.validation import (
    load_evaluation_dataset,
    verify_d_minus_1_integrity,
)


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class PredictivePipeline:
    """End-to-end execution pipeline for Phase 4C."""

    def __init__(self, config: Optional[PredictiveEngineConfig] = None):
        self.config = config or PredictiveEngineConfig()
        self.output_dir = PREDICTIVE_STORE_V4C_DIR
        self.analysis_dir = ANALYSIS_DIR
        self.docs_dir = DOCS_DIR
        
        # Ensure target directories exist
        for d in [self.output_dir, self.analysis_dir, self.docs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def run_predictions_on_df(
        self,
        df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Generate predictions, uncertainty intervals, and VORP for all rows in df.
        
        Returns:
            (bat_preds_df, bowl_preds_df, field_preds_df, vorp_df)
        """
        bat_records = []
        bowl_records = []
        field_records = []
        vorp_records = []

        for row in df.itertuples(index=False):
            player_id = row.player_id
            match_id = str(row.match_id)
            match_date = str(row.match_date)[:10]
            match_format = row.match_format
            year = int(row.year)
            role = row.inferred_role
            pos = row.batting_position if hasattr(row, "batting_position") else None
            pf = getattr(row, "park_factor", 1.0)
            obq = getattr(row, "opp_bowling_quality", 1.0)
            obatq = getattr(row, "opp_batting_quality", 1.0)

            # 1. Batting
            pre_r_bat = getattr(row, "pre_r_bat", 1000.0)
            pre_rd_bat = getattr(row, "pre_rd_bat", 350.0)
            bat_res = predict_batting_performance(
                pre_r_bat=pre_r_bat,
                pre_rd_bat=pre_rd_bat,
                match_format=match_format,
                batting_position=pos,
                inferred_role=role,
                park_factor=pf,
                opp_bowling_quality=obq,
                engine_config=self.config,
            )
            act_runs = getattr(row, "runs_scored", None)
            act_balls = getattr(row, "balls_faced", None)
            is_dismissed = getattr(row, "is_dismissed", None)

            bat_records.append({
                "player_id": player_id,
                "match_id": match_id,
                "match_date": match_date,
                "match_format": match_format,
                "year": year,
                "inferred_role": role,
                "batting_position": pos,
                "pre_r_bat": pre_r_bat,
                "pre_rd_bat": pre_rd_bat,
                "expected_balls_faced": bat_res["expected_balls_faced"],
                "expected_scoring_rate": bat_res["expected_scoring_rate"],
                "expected_runs": bat_res["expected_runs"],
                "runs_total_variance": bat_res["runs_total_variance"],
                "runs_interval_50_low": bat_res["runs_interval_50"][0],
                "runs_interval_50_high": bat_res["runs_interval_50"][1],
                "runs_interval_80_low": bat_res["runs_interval_80"][0],
                "runs_interval_80_high": bat_res["runs_interval_80"][1],
                "runs_interval_90_low": bat_res["runs_interval_90"][0],
                "runs_interval_90_high": bat_res["runs_interval_90"][1],
                "runs_interval_95_low": bat_res["runs_interval_95"][0],
                "runs_interval_95_high": bat_res["runs_interval_95"][1],
                "dismissal_probability": bat_res["dismissal_probability"],
                "expected_boundary_rate": bat_res["expected_boundary_rate"],
                "actual_runs_scored": act_runs,
                "actual_balls_faced": act_balls,
                "actual_is_dismissed": is_dismissed,
            })

            # 2. Bowling
            pre_r_bowl = getattr(row, "pre_r_bowl", 1000.0)
            pre_rd_bowl = getattr(row, "pre_rd_bowl", 350.0)
            bowl_res = predict_bowling_performance(
                pre_r_bowl=pre_r_bowl,
                pre_rd_bowl=pre_rd_bowl,
                match_format=match_format,
                inferred_role=role,
                park_factor=pf,
                opp_batting_quality=obatq,
                engine_config=self.config,
            )
            act_balls_bowled = getattr(row, "legal_balls_bowled", None)
            act_runs_conceded = getattr(row, "runs_conceded", None)
            act_wkts = getattr(row, "wickets_taken", None)

            bowl_records.append({
                "player_id": player_id,
                "match_id": match_id,
                "match_date": match_date,
                "match_format": match_format,
                "year": year,
                "inferred_role": role,
                "pre_r_bowl": pre_r_bowl,
                "pre_rd_bowl": pre_rd_bowl,
                "expected_balls_bowled": bowl_res["expected_balls_bowled"],
                "expected_overs_bowled": bowl_res["expected_overs_bowled"],
                "expected_hazard_rate": bowl_res["expected_hazard_rate"],
                "expected_economy_rate": bowl_res["expected_economy_rate"],
                "expected_wickets": bowl_res["expected_wickets"],
                "wickets_total_variance": bowl_res["wickets_total_variance"],
                "wickets_interval_50_low": bowl_res["wickets_interval_50"][0],
                "wickets_interval_50_high": bowl_res["wickets_interval_50"][1],
                "wickets_interval_90_low": bowl_res["wickets_interval_90"][0],
                "wickets_interval_90_high": bowl_res["wickets_interval_90"][1],
                "expected_runs_conceded": bowl_res["expected_runs_conceded"],
                "runs_conceded_total_variance": bowl_res["runs_conceded_total_variance"],
                "runs_conceded_interval_50_low": bowl_res["runs_conceded_interval_50"][0],
                "runs_conceded_interval_50_high": bowl_res["runs_conceded_interval_50"][1],
                "runs_conceded_interval_90_low": bowl_res["runs_conceded_interval_90"][0],
                "runs_conceded_interval_90_high": bowl_res["runs_conceded_interval_90"][1],
                "expected_dot_pct": bowl_res["expected_dot_pct"],
                "actual_legal_balls_bowled": act_balls_bowled,
                "actual_runs_conceded": act_runs_conceded,
                "actual_wickets_taken": act_wkts,
            })

            # 3. Fielding
            pre_r_field = getattr(row, "pre_r_field", 500.0)
            pre_rd_field = getattr(row, "pre_rd_field", 350.0)
            field_res = predict_fielding_performance(
                pre_r_field=pre_r_field,
                pre_rd_field=pre_rd_field,
                match_format=match_format,
                inferred_role=role,
                engine_config=self.config,
            )
            act_catches = getattr(row, "catches_taken", None)
            act_involvements = getattr(row, "total_fielding_involvements", None)

            field_records.append({
                "player_id": player_id,
                "match_id": match_id,
                "match_date": match_date,
                "match_format": match_format,
                "year": year,
                "inferred_role": role,
                "pre_r_field": pre_r_field,
                "pre_rd_field": pre_rd_field,
                "is_wicketkeeper": field_res["is_wicketkeeper"],
                "expected_involvements": field_res["expected_involvements"],
                "fielding_total_variance": field_res["fielding_total_variance"],
                "fielding_interval_90_low": field_res["fielding_interval_90"][0],
                "fielding_interval_90_high": field_res["fielding_interval_90"][1],
                "expected_fielding_run_value": field_res["expected_fielding_run_value"],
                "actual_catches_taken": act_catches,
                "actual_fielding_involvements": act_involvements,
            })

            # 4. VORP Valuation
            vorp_res = calculate_player_vorp(
                pre_r_bat=pre_r_bat,
                pre_rd_bat=pre_rd_bat,
                pre_r_bowl=pre_r_bowl,
                pre_rd_bowl=pre_rd_bowl,
                pre_r_field=pre_r_field,
                pre_rd_field=pre_rd_field,
                match_format=match_format,
                batting_position=pos,
                inferred_role=role,
                park_factor=pf,
                opp_bowling_quality=obq,
                opp_batting_quality=obatq,
                engine_config=self.config,
            )
            vorp_records.append({
                "player_id": player_id,
                "match_id": match_id,
                "match_date": match_date,
                "match_format": match_format,
                "year": year,
                "inferred_role": role,
                "vorp_bat": vorp_res["vorp_bat"],
                "vorp_bowl": vorp_res["vorp_bowl"],
                "vorp_field": vorp_res["vorp_field"],
                "vorp_total": vorp_res["vorp_total"],
                "is_above_replacement": vorp_res["is_above_replacement"],
                "rep_r_bat": vorp_res["rep_r_bat"],
                "rep_r_bowl": vorp_res["rep_r_bowl"],
                "rep_r_field": vorp_res["rep_r_field"],
            })

        return (
            pd.DataFrame(bat_records),
            pd.DataFrame(bowl_records),
            pd.DataFrame(field_records),
            pd.DataFrame(vorp_records),
        )

    def write_partitioned_dataset(
        self,
        df: pd.DataFrame,
        base_subpath: str,
    ) -> List[Path]:
        """
        Write DataFrame to Hive partitioned directory structure:
            base_subpath/match_format=.../year=.../data.parquet
        Drops partition columns from inner Parquet schemas to avoid type conflicts.
        """
        target_root = self.output_dir / base_subpath
        target_root.mkdir(parents=True, exist_ok=True)
        written_files = []

        # Group by match_format and year
        for (fmt, yr), group in df.groupby(["match_format", "year"]):
            partition_dir = target_root / f"match_format={fmt}" / f"year={yr}"
            partition_dir.mkdir(parents=True, exist_ok=True)
            file_path = partition_dir / f"{base_subpath}.parquet"
            
            # Drop partition columns from inner schema
            inner_df = group.drop(columns=["match_format", "year"], errors="ignore")
            inner_table = pa.Table.from_pandas(inner_df)
            pq.write_table(inner_table, file_path, compression="snappy")
            written_files.append(file_path)

        return written_files

    def evaluate_benchmarks_and_calibration(
        self,
        df_full: pd.DataFrame,
        bat_preds: pd.DataFrame,
        bowl_preds: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Run comprehensive baseline comparison and calibration diagnostics.
        """
        # Merge actuals and baselines with predictions
        eval_df = df_full.copy()
        
        # 1. Batting Evaluation (filter to players who batted)
        bat_eval = bat_preds[bat_preds["actual_runs_scored"].notna()].copy()
        act_runs = bat_eval["actual_runs_scored"].to_numpy(dtype=float)
        pred_runs_4c = bat_eval["expected_runs"].to_numpy(dtype=float)
        
        # Intervals 90%
        ints_90_4c = list(zip(bat_eval["runs_interval_90_low"], bat_eval["runs_interval_90_high"]))
        tot_vars_4c = bat_eval["runs_total_variance"].to_numpy(dtype=float)

        # Baseline 0: Format Global Mean
        bm0_pred = np.full_like(act_runs, np.mean(act_runs) if len(act_runs) > 0 else 20.0)

        # Baseline 1: 10-match Rolling Average
        if "rolling_batting_avg" in eval_df.columns:
            bm1_series = eval_df.loc[bat_eval.index, "rolling_batting_avg"].astype(float).fillna(float(np.mean(act_runs))).to_numpy(dtype=float)
        else:
            bm1_series = bm0_pred.copy()

        # Baseline 2: 365-day EWMA (decayed strike rate * balls)
        if "decayed_batting_sr" in eval_df.columns and "actual_balls_faced" in bat_eval.columns:
            sr = eval_df.loc[bat_eval.index, "decayed_batting_sr"].astype(float).fillna(100.0).to_numpy(dtype=float) / 100.0
            balls = bat_eval["expected_balls_faced"].to_numpy(dtype=float)
            bm2_pred = sr * balls
        else:
            bm2_pred = bm0_pred.copy()

        # Baseline 3: Exposure-adjusted Rate Baseline (rolling SR * exp_balls)
        if "rolling_batting_sr" in eval_df.columns:
            sr_roll = eval_df.loc[bat_eval.index, "rolling_batting_sr"].astype(float).fillna(100.0).to_numpy(dtype=float) / 100.0
            balls = bat_eval["expected_balls_faced"].to_numpy(dtype=float)
            bm3_pred = sr_roll * balls
        else:
            bm3_pred = bm0_pred.copy()

        # Compute metrics
        m_bm0 = compute_regression_metrics(act_runs, bm0_pred)
        m_bm1 = compute_regression_metrics(act_runs, bm1_series)
        m_bm2 = compute_regression_metrics(act_runs, bm2_pred)
        m_bm3 = compute_regression_metrics(act_runs, bm3_pred)
        m_4c = compute_regression_metrics(act_runs, pred_runs_4c, ints_90_4c, tot_vars_4c)

        benchmark_rows = [
            {"discipline": "Batting", "model": "BM-0 (Format Global Mean)", **m_bm0},
            {"discipline": "Batting", "model": "BM-1 (10-Match Rolling Average)", **m_bm1},
            {"discipline": "Batting", "model": "BM-2 (365-Day EWMA Decay)", **m_bm2},
            {"discipline": "Batting", "model": "BM-3 (Exposure-Adjusted Rolling Rate)", **m_bm3},
            {"discipline": "Batting", "model": "Model 4C (CA-HBSS Calibrated Two-Stage)", **m_4c},
        ]

        # 2. Bowling Evaluation (filter to players who bowled)
        bowl_eval = bowl_preds[bowl_preds["actual_wickets_taken"].notna()].copy()
        if len(bowl_eval) > 0:
            act_wkts = bowl_eval["actual_wickets_taken"].to_numpy(dtype=float)
            pred_wkts_4c = bowl_eval["expected_wickets"].to_numpy(dtype=float)
            ints_90_w = list(zip(bowl_eval["wickets_interval_90_low"], bowl_eval["wickets_interval_90_high"]))
            vars_w = bowl_eval["wickets_total_variance"].to_numpy(dtype=float)

            bm0_wkts = np.full_like(act_wkts, np.mean(act_wkts))
            if "rolling_wickets_taken" in eval_df.columns:
                bm1_wkts = eval_df.loc[bowl_eval.index, "rolling_wickets_taken"].astype(float).fillna(float(np.mean(act_wkts))).to_numpy(dtype=float) / 10.0
            else:
                bm1_wkts = bm0_wkts.copy()

            m_bowl_bm0 = compute_regression_metrics(act_wkts, bm0_wkts)
            m_bowl_bm1 = compute_regression_metrics(act_wkts, bm1_wkts)
            m_bowl_4c = compute_regression_metrics(act_wkts, pred_wkts_4c, ints_90_w, vars_w)

            benchmark_rows.extend([
                {"discipline": "Bowling Wickets", "model": "BM-0 (Format Global Mean)", **m_bowl_bm0},
                {"discipline": "Bowling Wickets", "model": "BM-1 (10-Match Rolling Wickets)", **m_bowl_bm1},
                {"discipline": "Bowling Wickets", "model": "Model 4C (CA-HBSS Calibrated Hazard)", **m_bowl_4c},
            ])

        benchmarks_df = pd.DataFrame(benchmark_rows)

        # 3. Calibration Diagnostics for Model 4C Batting Runs
        cov_50 = evaluate_interval_coverage(
            list(act_runs),
            list(zip(bat_eval["runs_interval_50_low"], bat_eval["runs_interval_50_high"])),
            nominal_rate=0.50,
        )
        cov_80 = evaluate_interval_coverage(
            list(act_runs),
            list(zip(bat_eval["runs_interval_80_low"], bat_eval["runs_interval_80_high"])),
            nominal_rate=0.80,
        )
        cov_90 = evaluate_interval_coverage(
            list(act_runs),
            list(zip(bat_eval["runs_interval_90_low"], bat_eval["runs_interval_90_high"])),
            nominal_rate=0.90,
        )
        cov_95 = evaluate_interval_coverage(
            list(act_runs),
            list(zip(bat_eval["runs_interval_95_low"], bat_eval["runs_interval_95_high"])),
            nominal_rate=0.95,
        )

        calib_curve = compute_calibration_curve(list(pred_runs_4c), list(act_runs), n_bins=10)

        calibration_rows = [
            {"diagnostic_type": "Coverage", "target_nominal": 0.50, "empirical_rate": cov_50["empirical_rate"], "error": cov_50["coverage_error"], "details": json.dumps(cov_50)},
            {"diagnostic_type": "Coverage", "target_nominal": 0.80, "empirical_rate": cov_80["empirical_rate"], "error": cov_80["coverage_error"], "details": json.dumps(cov_80)},
            {"diagnostic_type": "Coverage", "target_nominal": 0.90, "empirical_rate": cov_90["empirical_rate"], "error": cov_90["coverage_error"], "details": json.dumps(cov_90)},
            {"diagnostic_type": "Coverage", "target_nominal": 0.95, "empirical_rate": cov_95["empirical_rate"], "error": cov_95["coverage_error"], "details": json.dumps(cov_95)},
            {"diagnostic_type": "Reliability Diagram", "target_nominal": 1.00, "empirical_rate": calib_curve["calibration_slope"], "error": calib_curve["calibration_intercept"], "details": json.dumps(calib_curve)},
        ]
        calibration_df = pd.DataFrame(calibration_rows)

        return benchmarks_df, calibration_df

    def execute(self) -> Dict[str, Any]:
        """Execute the complete Phase 4C production pipeline."""
        start_time = time.time()
        print("=== Starting CricEngine AI Phase 4C Production Pipeline ===")

        # Step 1: Load Datasets
        print("1. Loading Holdout Out-of-Sample Dataset (2024-2026)...")
        holdout_df = load_evaluation_dataset(split="holdout", include_rolling=True)
        print(f"   Holdout dataset loaded: {len(holdout_df):,} player-match observations.")
        
        d1_check = verify_d_minus_1_integrity(holdout_df)
        print(f"   D-1 Batch Boundary Check: {d1_check['status']} ({d1_check['violations']} violations).")

        print("2. Loading Historical Validation Dataset (2020-2023)...")
        val_df = load_evaluation_dataset(split="validation", include_rolling=True)
        print(f"   Validation dataset loaded: {len(val_df):,} player-match observations.")

        # Step 2: Generate Predictions across Validation & Holdout
        print("3. Generating Calibrated Predictions & Uncertainty Intervals...")
        all_eval_df = pd.concat([val_df, holdout_df], ignore_index=True)
        bat_preds, bowl_preds, field_preds, vorp_preds = self.run_predictions_on_df(all_eval_df)
        print(f"   Generated {len(bat_preds):,} batting predictions.")
        print(f"   Generated {len(bowl_preds):,} bowling predictions.")
        print(f"   Generated {len(field_preds):,} fielding predictions.")
        print(f"   Generated {len(vorp_preds):,} VORP evaluations.")

        # Step 3: Materialize Partitioned Parquet Stores
        print("4. Materializing Hive-Partitioned Parquet Datasets into predictive_store_v4c/...")
        all_files = []
        all_files.extend(self.write_partitioned_dataset(bat_preds, "batting_predictions"))
        all_files.extend(self.write_partitioned_dataset(bowl_preds, "bowling_predictions"))
        all_files.extend(self.write_partitioned_dataset(field_preds, "fielding_predictions"))
        all_files.extend(self.write_partitioned_dataset(vorp_preds, "player_match_vorp"))

        # Step 4: Run Benchmark & Calibration Evaluations
        print("5. Running Benchmark Baseline Comparisons and Calibration Diagnostics...")
        benchmarks_df, calibration_df = self.evaluate_benchmarks_and_calibration(
            all_eval_df, bat_preds, bowl_preds
        )

        metrics_dir = self.output_dir / "evaluation_metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        bm_file = metrics_dir / "benchmark_comparison.parquet"
        cal_file = metrics_dir / "calibration_diagnostics.parquet"
        pq.write_table(pa.Table.from_pandas(benchmarks_df), bm_file)
        pq.write_table(pa.Table.from_pandas(calibration_df), cal_file)
        all_files.extend([bm_file, cal_file])

        # Step 5: VORP Surplus Ratio Evaluation
        surplus_ratio = compute_pool_surplus_ratio(list(vorp_preds["vorp_total"]))
        print(f"   Aggregate VORP Surplus Ratio: {surplus_ratio:.3f}x")

        # Step 6: Generate Cryptographic Manifest
        print("6. Computing SHA-256 Checksums and Generating _manifest.json...")
        manifest_files = {}
        for f in sorted(all_files):
            rel_path = str(f.relative_to(self.output_dir))
            manifest_files[rel_path] = {
                "sha256": compute_file_sha256(f),
                "bytes": f.stat().st_size,
            }

        manifest = {
            "version": self.config.version,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_files": len(manifest_files),
            "files": manifest_files,
            "summary": {
                "total_batting_predictions": len(bat_preds),
                "total_bowling_predictions": len(bowl_preds),
                "total_fielding_predictions": len(field_preds),
                "total_vorp_records": len(vorp_preds),
                "vorp_surplus_ratio": surplus_ratio,
                "d_minus_1_verified": d1_check["status"] == "PASS",
            },
        }

        manifest_path = self.output_dir / "_manifest.json"
        with open(manifest_path, "w") as mf:
            json.dump(manifest, mf, indent=2)

        # Step 7: Export Analysis Artifacts
        print("7. Exporting Analytical Artifacts to data/analysis/phase_4c/...")
        benchmarks_df.to_json(self.analysis_dir / "benchmark_comparison.json", orient="records", indent=2)
        calibration_df.to_json(self.analysis_dir / "calibration_diagnostics.json", orient="records", indent=2)
        with open(self.analysis_dir / "pipeline_summary.json", "w") as pf:
            json.dump(manifest["summary"], pf, indent=2)

        elapsed = time.time() - start_time
        print(f"=== Phase 4C Production Pipeline Complete in {elapsed:.1f}s ===")
        print(f"   Materialized files: {len(all_files)}")
        print(f"   Manifest: {manifest_path}")

        return manifest


if __name__ == "__main__":
    pipeline = PredictivePipeline()
    pipeline.execute()
