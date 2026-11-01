"""
CricEngine AI — Calibrated Two-Stage Bowling Predictive Model (Phase 4C)

Implements:
1. Stage 1: Opportunity/Exposure model (expected legal balls bowled based on format and role)
2. Stage 2: Dual Efficiency model:
   - Wicket hazard rate (calibrated log-link GLM linking latent rating theta to hazard)
   - Economy rate (calibrated log-link GLM linking latent rating theta to runs/over)
3. Total Variance Integration & Central Prediction Intervals for Wickets & Runs Conceded
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


def get_expected_balls_bowled(
    format_code: str,
    inferred_role: Optional[str] = None,
    participation_role: Optional[str] = None,
) -> float:
    """
    Stage 1 Exposure Model:
    Determine expected legal balls bowled conditional on format and role.
    """
    fmt_key = "TEST" if format_code.upper() in ("TEST", "TESTS") else format_code.upper()
    cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])
    
    role = inferred_role or ""
    # Pure wicketkeeper never bowls
    if role == "R4_WICKETKEEPER":
        return 0.0

    return cfg.role_balls_bowled.get(role, 0.0)


def predict_bowling_performance(
    pre_r_bowl: float,
    pre_rd_bowl: float,
    match_format: str,
    inferred_role: Optional[str] = None,
    participation_role: Optional[str] = None,
    park_factor: float = 1.0,
    opp_batting_quality: float = 1.0,
    engine_config: Optional[PredictiveEngineConfig] = None,
) -> Dict[str, Any]:
    """
    Predict match bowling performance (wickets and runs conceded) and interval distributions.
    
    Returns:
        dict containing:
            - expected_balls_bowled
            - expected_overs_bowled
            - expected_hazard_rate
            - expected_economy_rate
            - expected_wickets
            - wickets_total_variance
            - wickets_interval_50, 80, 90, 95
            - expected_runs_conceded
            - runs_conceded_total_variance
            - runs_conceded_interval_50, 80, 90, 95
            - expected_dot_pct
    """
    if engine_config is None:
        engine_config = PredictiveEngineConfig()

    fmt_key = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
    fmt_cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])

    # Stage 1: Exposure/Opportunity
    exp_balls = get_expected_balls_bowled(fmt_key, inferred_role, participation_role)
    exp_overs = round(exp_balls / 6.0, 1)

    if exp_balls <= 0.0:
        return {
            "expected_balls_bowled": 0.0,
            "expected_overs_bowled": 0.0,
            "expected_hazard_rate": 0.0,
            "expected_economy_rate": round(fmt_cfg.baseline_economy_rate, 2),
            "expected_wickets": 0.0,
            "wickets_total_variance": 0.0,
            "wickets_aleatoric_variance": 0.0,
            "wickets_epistemic_variance": 0.0,
            "wickets_interval_50": (0.0, 0.0),
            "wickets_interval_80": (0.0, 0.0),
            "wickets_interval_90": (0.0, 0.0),
            "wickets_interval_95": (0.0, 0.0),
            "expected_runs_conceded": 0.0,
            "runs_conceded_total_variance": 0.0,
            "runs_conceded_aleatoric_variance": 0.0,
            "runs_conceded_epistemic_variance": 0.0,
            "runs_conceded_interval_50": (0.0, 0.0),
            "runs_conceded_interval_80": (0.0, 0.0),
            "runs_conceded_interval_90": (0.0, 0.0),
            "runs_conceded_interval_95": (0.0, 0.0),
            "expected_dot_pct": 0.0,
        }

    # Standardized latent rating & epistemic uncertainty
    z_bowl = (pre_r_bowl - engine_config.native_mean) / engine_config.native_scale
    sigma_z = max(0.01, pre_rd_bowl / engine_config.native_scale)

    # Contextual bounds
    pf = max(0.65, min(1.50, park_factor if not pd.isna(park_factor) else 1.0))
    obatq = max(0.50, min(2.00, opp_batting_quality if not pd.isna(opp_batting_quality) else 1.0))

    # Stage 2A: Wicket Hazard Model
    beta_haz = engine_config.beta_bowl_haz
    context_haz = (1.0 / (pf ** engine_config.park_factor_power_bowl)) * (1.0 / (obatq ** engine_config.opp_batting_power_bowl))
    exp_hazard = fmt_cfg.baseline_hazard_rate * math.exp(beta_haz * z_bowl) * context_haz
    exp_wickets = exp_balls * exp_hazard * math.exp(0.5 * (beta_haz ** 2) * (sigma_z ** 2))

    tot_var_w, alea_var_w, epist_var_w = compute_total_variance(
        mu_point=exp_wickets,
        exposure=exp_balls,
        beta=beta_haz,
        rd=pre_rd_bowl,
        dispersion_alpha=engine_config.dispersion_bowl_wickets,
        native_scale=engine_config.native_scale,
    )
    intervals_w = compute_prediction_intervals(exp_wickets, tot_var_w)

    # Stage 2B: Economy Containment Model
    beta_econ = engine_config.beta_bowl_econ
    context_econ = (pf ** engine_config.park_factor_power_bat) * (obatq ** engine_config.opp_batting_power_bowl)
    exp_economy = fmt_cfg.baseline_economy_rate * math.exp(-beta_econ * z_bowl) * context_econ
    exp_runs_conceded = (exp_balls / 6.0) * exp_economy * math.exp(0.5 * (beta_econ ** 2) * (sigma_z ** 2))

    tot_var_r, alea_var_r, epist_var_r = compute_total_variance(
        mu_point=exp_runs_conceded,
        exposure=exp_balls,
        beta=beta_econ,
        rd=pre_rd_bowl,
        dispersion_alpha=engine_config.dispersion_bowl_runs,
        native_scale=engine_config.native_scale,
    )
    intervals_r = compute_prediction_intervals(exp_runs_conceded, tot_var_r)

    # Stage 2C: Dot Ball Percentage
    base_dot = 0.38 if fmt_key == "T20" else (0.50 if fmt_key == "ODI" else 0.72)
    exp_dot = max(0.15, min(0.90, base_dot * math.exp(0.08 * z_bowl)))

    return {
        "expected_balls_bowled": round(exp_balls, 1),
        "expected_overs_bowled": exp_overs,
        "expected_hazard_rate": round(exp_hazard, 4),
        "expected_economy_rate": round(exp_economy, 2),
        "expected_wickets": round(exp_wickets, 2),
        "wickets_total_variance": round(tot_var_w, 2),
        "wickets_aleatoric_variance": round(alea_var_w, 2),
        "wickets_epistemic_variance": round(epist_var_w, 2),
        "wickets_interval_50": intervals_w["interval_50"],
        "wickets_interval_80": intervals_w["interval_80"],
        "wickets_interval_90": intervals_w["interval_90"],
        "wickets_interval_95": intervals_w["interval_95"],
        "expected_runs_conceded": round(exp_runs_conceded, 2),
        "runs_conceded_total_variance": round(tot_var_r, 2),
        "runs_conceded_aleatoric_variance": round(alea_var_r, 2),
        "runs_conceded_epistemic_variance": round(epist_var_r, 2),
        "runs_conceded_interval_50": intervals_r["interval_50"],
        "runs_conceded_interval_80": intervals_r["interval_80"],
        "runs_conceded_interval_90": intervals_r["interval_90"],
        "runs_conceded_interval_95": intervals_r["interval_95"],
        "expected_dot_pct": round(exp_dot, 3),
    }
