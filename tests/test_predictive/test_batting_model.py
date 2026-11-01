"""
Unit tests for batting predictive model (Phase 4C).
"""

import pytest
import math
from src.predictive.config import FORMAT_CONFIGS, PredictiveEngineConfig
from src.predictive.batting_model import (
    get_expected_balls_faced,
    predict_batting_performance,
)


def test_batting_exposure_by_position():
    """Verify expected balls faced diminishes monotonically down the order."""
    t20_opener = get_expected_balls_faced("T20", batting_position=1)
    t20_middle = get_expected_balls_faced("T20", batting_position=5)
    t20_tail = get_expected_balls_faced("T20", batting_position=10)
    
    assert t20_opener > t20_middle > t20_tail
    assert t20_opener == 26.5
    assert t20_tail == 2.0


def test_batting_exposure_role_fallback():
    """Verify role fallback when position is missing."""
    balls_opener = get_expected_balls_faced("T20", batting_position=None, inferred_role="R1_OPENER")
    balls_pacer = get_expected_balls_faced("T20", batting_position=None, inferred_role="R8_PACE_SPECIALIST")
    
    assert balls_opener == 26.5
    assert balls_pacer == 2.0


def test_batting_rate_and_jensen_correction():
    """Verify elite batsman gets higher predicted runs than average, with Jensen inequality adjustment."""
    cfg = PredictiveEngineConfig()
    avg_pred = predict_batting_performance(
        pre_r_bat=1000.0,
        pre_rd_bat=150.0,
        match_format="T20",
        batting_position=3,
        engine_config=cfg,
    )
    elite_pred = predict_batting_performance(
        pre_r_bat=1350.0,  # +1.0 SD
        pre_rd_bat=50.0,
        match_format="T20",
        batting_position=3,
        engine_config=cfg,
    )
    
    assert elite_pred["expected_runs"] > avg_pred["expected_runs"]
    assert elite_pred["expected_scoring_rate"] > avg_pred["expected_scoring_rate"]
    assert elite_pred["dismissal_probability"] < avg_pred["dismissal_probability"]


def test_batting_contextual_adjustments():
    """Verify park factor increases expected runs and opposition bowling quality decreases it."""
    neutral = predict_batting_performance(1000.0, 100.0, "ODI", 4, park_factor=1.0, opp_bowling_quality=1.0)
    batting_paradise = predict_batting_performance(1000.0, 100.0, "ODI", 4, park_factor=1.25, opp_bowling_quality=1.0)
    tough_attack = predict_batting_performance(1000.0, 100.0, "ODI", 4, park_factor=1.0, opp_bowling_quality=1.40)
    
    assert batting_paradise["expected_runs"] > neutral["expected_runs"]
    assert tough_attack["expected_runs"] < neutral["expected_runs"]


def test_batting_interval_monotonicity():
    """Verify central prediction intervals are properly nested and monotonic."""
    pred = predict_batting_performance(1150.0, 120.0, "TEST", 3)
    
    l95, u95 = pred["runs_interval_95"]
    l90, u90 = pred["runs_interval_90"]
    l80, u80 = pred["runs_interval_80"]
    l50, u50 = pred["runs_interval_50"]
    
    assert l95 <= l90 <= l80 <= l50
    assert u50 <= u80 <= u90 <= u95
    assert pred["runs_total_variance"] > pred["runs_aleatoric_variance"]
    assert pred["runs_epistemic_variance"] > 0.0
