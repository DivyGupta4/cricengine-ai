"""
CricEngine AI — All-Round Value & Multi-Discipline Net Contribution (Phase 4C)

Combines predicted marginal value across batting, bowling, and fielding into a unified net run contribution.
Mandate: Strictly additive, RosterSynergyBonus = 0.0 (no arbitrary non-linear multi-role bonuses).
"""

from __future__ import annotations
from typing import Dict, Any, Optional

from src.predictive.config import FORMAT_CONFIGS, PredictiveEngineConfig
from src.predictive.batting_model import predict_batting_performance
from src.predictive.bowling_model import predict_bowling_performance
from src.predictive.fielding_model import predict_fielding_performance


def predict_allround_net_contribution(
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
    Compute total additive match valuation in run equivalents.
    """
    if engine_config is None:
        engine_config = PredictiveEngineConfig()

    fmt_key = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
    fmt_cfg = FORMAT_CONFIGS.get(fmt_key, FORMAT_CONFIGS["T20"])

    # 1. Batting
    bat_pred = predict_batting_performance(
        pre_r_bat=pre_r_bat,
        pre_rd_bat=pre_rd_bat,
        match_format=fmt_key,
        batting_position=batting_position,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_bowling_quality=opp_bowling_quality,
        engine_config=engine_config,
    )

    # 2. Bowling
    bowl_pred = predict_bowling_performance(
        pre_r_bowl=pre_r_bowl,
        pre_rd_bowl=pre_rd_bowl,
        match_format=fmt_key,
        inferred_role=inferred_role,
        park_factor=park_factor,
        opp_batting_quality=opp_batting_quality,
        engine_config=engine_config,
    )

    # 3. Fielding
    field_pred = predict_fielding_performance(
        pre_r_field=pre_r_field,
        pre_rd_field=pre_rd_field,
        match_format=fmt_key,
        inferred_role=inferred_role,
        engine_config=engine_config,
    )

    # Baseline expectations for identical exposure
    base_bat_runs = bat_pred["expected_balls_faced"] * fmt_cfg.baseline_scoring_rate
    batting_net_runs = bat_pred["expected_runs"] - base_bat_runs

    balls_bowled = bowl_pred["expected_balls_bowled"]
    if balls_bowled > 0.0:
        base_bowl_runs = (balls_bowled / 6.0) * fmt_cfg.baseline_economy_rate
        base_bowl_wkts = balls_bowled * fmt_cfg.baseline_hazard_rate
        
        # Runs saved relative to baseline + run value of surplus wickets
        runs_saved = base_bowl_runs - bowl_pred["expected_runs_conceded"]
        wicket_surplus = (bowl_pred["expected_wickets"] - base_bowl_wkts) * fmt_cfg.wicket_run_value
        bowling_net_runs = runs_saved + wicket_surplus
    else:
        bowling_net_runs = 0.0

    fielding_net_runs = field_pred["expected_fielding_run_value"] - (
        (1.10 if field_pred["is_wicketkeeper"] else 0.35) * fmt_cfg.catch_run_value
    )

    total_net_runs = batting_net_runs + bowling_net_runs + fielding_net_runs

    return {
        "batting_predicted_runs": bat_pred["expected_runs"],
        "batting_net_runs": round(batting_net_runs, 2),
        "bowling_predicted_wickets": bowl_pred["expected_wickets"],
        "bowling_predicted_runs_conceded": bowl_pred["expected_runs_conceded"],
        "bowling_net_runs": round(bowling_net_runs, 2),
        "fielding_involvements": field_pred["expected_involvements"],
        "fielding_net_runs": round(fielding_net_runs, 2),
        "total_net_runs": round(total_net_runs, 2),
        "roster_synergy_bonus": 0.0,  # Strictly zero
        "batting_pred": bat_pred,
        "bowl_pred": bowl_pred,
        "field_pred": field_pred,
    }
