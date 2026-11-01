"""
CricEngine AI — Calibrated Two-Stage Batting Predictive Model (Phase 4C)

Implements:
1. Stage 1: Exposure/Opportunity model (expected balls faced based on format, position, and role)
2. Stage 2: Rate/Efficiency model (calibrated log-link GLM linking latent rating theta to scoring rate)
3. Total Variance Integration & Central Prediction Intervals (50%, 80%, 90%, 95%)
"""

from __future__ import annotations
import math
from typing import Dict, Any, Optional, Tuple
import numpy as np
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


def get_expected_balls_faced(
    format_code: str,
    batting_position: Optional[int] = None,
    inferred_role: Optional[str] = None,
) -> float:
    """
    Stage 1 Exposure Model:
    Determine expected balls faced conditional on format, batting position, and role.
    """
    fmt_key = "TEST" if format_code.upper() in ("TEST", "TESTS") else format_code.upper()
    cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])
    
    # 1. Direct batting position if valid integer in [1, 11]
    if batting_position is not None and not pd.isna(batting_position):
        try:
            pos = int(batting_position)
            if 1 <= pos <= 11:
                return cfg.position_balls_faced.get(pos, 10.0)
        except (ValueError, TypeError):
            pass

    # 2. Inferred role mapping fallback
    role_to_pos = {
        "R1_OPENER": 1,
        "R2_TOP_ORDER": 3,
        "R3_MIDDLE_ORDER": 5,
        "R4_WICKETKEEPER": 6,
        "R5_BATTING_ALLROUNDER": 6,
        "R6_BOWLING_ALLROUNDER": 8,
        "R7_SPIN_SPECIALIST": 10,
        "R8_PACE_SPECIALIST": 10,
    }
    pos_fallback = role_to_pos.get(inferred_role or "", 6)
    return cfg.position_balls_faced.get(pos_fallback, 12.0)


def predict_batting_performance(
    pre_r_bat: float,
    pre_rd_bat: float,
    match_format: str,
    batting_position: Optional[int] = None,
    inferred_role: Optional[str] = None,
    park_factor: float = 1.0,
    opp_bowling_quality: float = 1.0,
    engine_config: Optional[PredictiveEngineConfig] = None,
) -> Dict[str, Any]:
    """
    Predict match batting performance and interval distribution.
    
    Returns:
        dict containing:
            - expected_balls_faced
            - expected_scoring_rate
            - expected_runs
            - runs_total_variance
            - runs_aleatoric_variance
            - runs_epistemic_variance
            - runs_interval_50: (low, high)
            - runs_interval_80: (low, high)
            - runs_interval_90: (low, high)
            - runs_interval_95: (low, high)
            - dismissal_probability
            - expected_boundary_rate
    """
    if engine_config is None:
        engine_config = PredictiveEngineConfig()

    fmt_key = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
    fmt_cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])

    # Stage 1: Opportunity/Exposure
    exp_balls = get_expected_balls_faced(fmt_key, batting_position, inferred_role)
    
    # Standardized rating & epistemic uncertainty
    z_bat = (pre_r_bat - engine_config.native_mean) / engine_config.native_scale
    sigma_z = max(0.01, pre_rd_bat / engine_config.native_scale)
    
    # Safe bounds on contextual factors
    pf = max(0.65, min(1.50, park_factor if not pd.isna(park_factor) else 1.0))
    obq = max(0.50, min(2.00, opp_bowling_quality if not pd.isna(opp_bowling_quality) else 1.0))

    # Stage 2: Scoring Rate
    # Rate = lambda_0 * exp(beta * z) * (pf / obq)
    beta = engine_config.beta_bat_rate
    context_mult = (pf ** engine_config.park_factor_power_bat) / (obq ** engine_config.opp_bowling_power_bat)
    exp_scoring_rate = fmt_cfg.baseline_scoring_rate * math.exp(beta * z_bat) * context_mult
    
    # Expected unconditional runs with Jensen's inequality correction
    exp_runs = exp_balls * exp_scoring_rate * math.exp(0.5 * (beta ** 2) * (sigma_z ** 2))
    
    # Stage 3: Law of Total Variance & Intervals
    tot_var, alea_var, epist_var = compute_total_variance(
        mu_point=exp_runs,
        exposure=exp_balls,
        beta=beta,
        rd=pre_rd_bat,
        dispersion_alpha=engine_config.dispersion_bat_runs,
        native_scale=engine_config.native_scale,
    )
    intervals = compute_prediction_intervals(exp_runs, tot_var)

    # Stage 4: Dismissal Probability
    base_hazard = fmt_cfg.baseline_hazard_rate
    # Better batting ability lowers per-ball dismissal hazard
    hazard_rate = base_hazard * math.exp(-0.15 * z_bat) * (obq / (pf ** 0.45))
    p_out = 1.0 - math.exp(-exp_balls * hazard_rate)
    p_out = max(0.05, min(0.98, p_out))

    # Stage 5: Expected Boundary Rate
    base_bnd = 0.165 if fmt_key == "T20" else (0.090 if fmt_key == "ODI" else 0.045)
    exp_boundary_rate = max(0.01, min(0.40, base_bnd * math.exp(0.12 * z_bat)))

    return {
        "expected_balls_faced": round(exp_balls, 1),
        "expected_scoring_rate": round(exp_scoring_rate, 4),
        "expected_runs": round(exp_runs, 2),
        "runs_total_variance": round(tot_var, 2),
        "runs_aleatoric_variance": round(alea_var, 2),
        "runs_epistemic_variance": round(epist_var, 2),
        "runs_interval_50": intervals["interval_50"],
        "runs_interval_80": intervals["interval_80"],
        "runs_interval_90": intervals["interval_90"],
        "runs_interval_95": intervals["interval_95"],
        "dismissal_probability": round(p_out, 4),
        "expected_boundary_rate": round(exp_boundary_rate, 4),
    }
