"""
Unit tests for bowling predictive model (Phase 4C).
"""

import pytest
from src.predictive.config import PredictiveEngineConfig
from src.predictive.bowling_model import (
    get_expected_balls_bowled,
    predict_bowling_performance,
)


def test_bowling_exposure_by_role():
    """Verify frontline bowlers get full quota while keepers and top order get zero/negligible balls."""
    pacer_balls = get_expected_balls_bowled("T20", inferred_role="R8_PACE_SPECIALIST")
    spinner_balls = get_expected_balls_bowled("T20", inferred_role="R7_SPIN_SPECIALIST")
    allrounder_balls = get_expected_balls_bowled("T20", inferred_role="R6_BOWLING_ALLROUNDER")
    keeper_balls = get_expected_balls_bowled("T20", inferred_role="R4_WICKETKEEPER")
    
    assert pacer_balls == 22.0
    assert spinner_balls == 22.0
    assert allrounder_balls == 18.0
    assert keeper_balls == 0.0


def test_bowling_dual_efficiency_and_intervals():
    """Verify elite bowler takes more wickets, concedes fewer runs, and intervals are monotonic."""
    avg_pred = predict_bowling_performance(
        pre_r_bowl=1000.0,
        pre_rd_bowl=150.0,
        match_format="ODI",
        inferred_role="R8_PACE_SPECIALIST",
    )
    elite_pred = predict_bowling_performance(
        pre_r_bowl=1350.0,
        pre_rd_bowl=60.0,
        match_format="ODI",
        inferred_role="R8_PACE_SPECIALIST",
    )
    
    assert elite_pred["expected_wickets"] > avg_pred["expected_wickets"]
    assert elite_pred["expected_runs_conceded"] < avg_pred["expected_runs_conceded"]
    assert elite_pred["expected_economy_rate"] < avg_pred["expected_economy_rate"]
    
    # Check interval nesting for wickets
    l90_w, u90_w = elite_pred["wickets_interval_90"]
    l50_w, u50_w = elite_pred["wickets_interval_50"]
    assert l90_w <= l50_w
    assert u50_w <= u90_w
    
    # Check interval nesting for runs conceded
    l90_r, u90_r = elite_pred["runs_conceded_interval_90"]
    l50_r, u50_r = elite_pred["runs_conceded_interval_50"]
    assert l90_r <= l50_r
    assert u50_r <= u90_r


def test_non_bowler_zero_predictions():
    """Verify pure non-bowler has zero expected overs, wickets, and variance."""
    non_bowler = predict_bowling_performance(
        pre_r_bowl=1000.0,
        pre_rd_bowl=350.0,
        match_format="T20",
        inferred_role="R4_WICKETKEEPER",
    )
    
    assert non_bowler["expected_balls_bowled"] == 0.0
    assert non_bowler["expected_wickets"] == 0.0
    assert non_bowler["expected_runs_conceded"] == 0.0
    assert non_bowler["wickets_total_variance"] == 0.0
