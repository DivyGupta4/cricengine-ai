"""
CricEngine AI — Empirically Grounded VORP Valuation Engine (Phase 4C)

Implements:
1. Format-specific empirical 10th percentile (P10) active replacement levels:
   - T20:  R_rep,bat = 740.0, R_rep,bowl = 1000.0, R_rep,field = 600.0
   - ODI:  R_rep,bat = 790.0, R_rep,bowl = 1000.0, R_rep,field = 625.0
   - TEST: R_rep,bat = 950.0, R_rep,bowl = 1000.0, R_rep,field = 720.0
2. Preservation of negative VORP values for sub-replacement performance
3. Uninformative prior replacement anchoring for bowling (theta = 0)
4. Valuation of surplus ratio across player pools
"""

from __future__ import annotations
import math
from typing import Dict, Any, Optional, List
import pandas as pd

from src.predictive.config import (
    FORMAT_CONFIGS,
    PredictiveFormatConfig,
    PredictiveEngineConfig,
)
from src.predictive.batting_model import predict_batting_performance
from src.predictive.bowling_model import predict_bowling_performance
from src.predictive.fielding_model import predict_fielding_performance


def calculate_player_vorp(
    pre_r_bat: float,
    pre_rd_bat: float,
    pre_r_bowl: float,
    pre_rd_bowl: float,
    pre_r_field: float,
    pre_rd_field: float,
    match_format: str,
    batting_position: Optional[int] = None,
    inferred_role: Optional[str] = None,
    park_factor: float = 1.0,
    opp_bowling_quality: float = 1.0,
    opp_batting_quality: float = 1.0,
    engine_config: Optional[PredictiveEngineConfig] = None,
) -> Dict[str, Any]:
    """
    Compute Value Over Replacement Player (VORP) in marginal run equivalents.
    Preserves negative VORP values (does NOT truncate at 0.0).
    """
    if engine_config is None:
        engine_config = PredictiveEngineConfig()

    fmt_key = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
    fmt_cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])

    rep_r_bat = fmt_cfg.replacement_r_bat
    rep_r_bowl = fmt_cfg.replacement_r_bowl
    rep_r_field = fmt_cfg.replacement_r_field

    # 1. Batting VORP
    # Actual player prediction
    pred_bat_act = predict_batting_performance(
        pre_r_bat=pre_r_bat,
        pre_rd_bat=pre_rd_bat,
        match_format=fmt_key,
        batting_position=batting_position,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_bowling_quality=opp_bowling_quality,
        engine_config=engine_config,
    )
    # Replacement player prediction (at replacement rating with nominal RD 350)
    pred_bat_rep = predict_batting_performance(
        pre_r_bat=rep_r_bat,
        pre_rd_bat=engine_config.native_scale,
        match_format=fmt_key,
        batting_position=batting_position,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_bowling_quality=opp_bowling_quality,
        engine_config=engine_config,
    )
    vorp_bat = pred_bat_act["expected_runs"] - pred_bat_rep["expected_runs"]

    # 2. Bowling VORP
    pred_bowl_act = predict_bowling_performance(
        pre_r_bowl=pre_r_bowl,
        pre_rd_bowl=pre_rd_bowl,
        match_format=fmt_key,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_batting_quality=opp_batting_quality,
        engine_config=engine_config,
    )
    pred_bowl_rep = predict_bowling_performance(
        pre_r_bowl=rep_r_bowl,
        pre_rd_bowl=engine_config.native_scale,
        match_format=fmt_key,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_batting_quality=opp_batting_quality,
        engine_config=engine_config,
    )
    if pred_bowl_act["expected_balls_bowled"] > 0.0:
        runs_saved_vs_rep = pred_bowl_rep["expected_runs_conceded"] - pred_bowl_act["expected_runs_conceded"]
        wkts_surplus_vs_rep = (pred_bowl_act["expected_wickets"] - pred_bowl_rep["expected_wickets"]) * fmt_cfg.wicket_run_value
        vorp_bowl = runs_saved_vs_rep + wkts_surplus_vs_rep
    else:
        vorp_bowl = 0.0

    # 3. Fielding VORP
    pred_field_act = predict_fielding_performance(
        pre_r_field=pre_r_field,
        pre_rd_field=pre_rd_field,
        match_format=fmt_key,
        inferred_role=inferred_role,
        engine_config=engine_config,
    )
    pred_field_rep = predict_fielding_performance(
        pre_r_field=rep_r_field,
        pre_rd_field=engine_config.native_scale,
        match_format=fmt_key,
        inferred_role=inferred_role,
        engine_config=engine_config,
    )
    vorp_field = (pred_field_act["expected_involvements"] - pred_field_rep["expected_involvements"]) * fmt_cfg.catch_run_value

    vorp_total = vorp_bat + vorp_bowl + vorp_field

    return {
        "vorp_bat": round(vorp_bat, 2),
        "vorp_bowl": round(vorp_bowl, 2),
        "vorp_field": round(vorp_field, 2),
        "vorp_total": round(vorp_total, 2),
        "is_above_replacement": vorp_total > 0.0,
        "rep_r_bat": rep_r_bat,
        "rep_r_bowl": rep_r_bowl,
        "rep_r_field": rep_r_field,
    }


def compute_pool_surplus_ratio(vorp_values: List[float]) -> float:
    """
    Compute aggregate surplus ratio for a distribution of player VORP values:
        Surplus Ratio = sum(max(0, VORP)) / sum(abs(VORP))
    """
    if not vorp_values:
        return 1.0
    pos_sum = sum(v for v in vorp_values if v > 0.0)
    total_abs = sum(abs(v) for v in vorp_values)
    if total_abs <= 0.0:
        return 1.0
    return round(pos_sum / total_abs, 3)
