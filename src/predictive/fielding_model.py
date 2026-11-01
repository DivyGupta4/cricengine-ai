"""
CricEngine AI — Fielding Predictive Model & Dismissal Involvement Engine (Phase 4C)

Models fielding involvement probability (catches, stumpings, run-outs)
enforcing a wide epistemic uncertainty floor (RD_field >= 150.0) reflecting observational noise.
"""

from __future__ import annotations
import math
from typing import Dict, Any, Optional
import pandas as pd

from src.predictive.config import (
    FORMAT_CONFIGS,
    PredictiveFormatConfig,
    PredictiveEngineConfig,
)
from src.predictive.uncertainty import (
    compute_total_variance,
    compute_prediction_intervals,
)


def predict_fielding_performance(
    pre_r_field: float,
    pre_rd_field: float,
    match_format: str,
    inferred_role: Optional[str] = None,
    engine_config: Optional[PredictiveEngineConfig] = None,
) -> Dict[str, Any]:
    """
    Predict match fielding involvements (catches, stumpings, runouts) and uncertainty intervals.
    """
    if engine_config is None:
        engine_config = PredictiveEngineConfig()

    fmt_key = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
    fmt_cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])

    # Enforce epistemic uncertainty floor
    effective_rd = max(engine_config.min_rd_floor_field, pre_rd_field)
    z_field = (pre_r_field - engine_config.field_native_mean) / engine_config.native_scale
    sigma_z = effective_rd / engine_config.native_scale

    # Base involvements conditioned on format and role
    is_keeper = (inferred_role == "R4_WICKETKEEPER")
    if fmt_key == "T20":
        base_inv = 1.10 if is_keeper else 0.35
    elif fmt_key == "ODI":
        base_inv = 1.65 if is_keeper else 0.45
    else:  # TEST
        base_inv = 3.20 if is_keeper else 0.85

    beta_field = engine_config.beta_field_inv
    exp_involvements = base_inv * math.exp(beta_field * z_field) * math.exp(0.5 * (beta_field ** 2) * (sigma_z ** 2))

    tot_var, alea_var, epist_var = compute_total_variance(
        mu_point=exp_involvements,
        exposure=base_inv,
        beta=beta_field,
        rd=effective_rd,
        dispersion_alpha=0.30,
        native_scale=engine_config.native_scale,
    )
    intervals = compute_prediction_intervals(exp_involvements, tot_var)
    exp_field_run_value = round(exp_involvements * fmt_cfg.catch_run_value, 2)

    return {
        "is_wicketkeeper": is_keeper,
        "expected_involvements": round(exp_involvements, 2),
        "fielding_total_variance": round(tot_var, 2),
        "fielding_aleatoric_variance": round(alea_var, 2),
        "fielding_epistemic_variance": round(epist_var, 2),
        "fielding_interval_50": intervals["interval_50"],
        "fielding_interval_80": intervals["interval_80"],
        "fielding_interval_90": intervals["interval_90"],
        "fielding_interval_95": intervals["interval_95"],
        "expected_fielding_run_value": exp_field_run_value,
    }
