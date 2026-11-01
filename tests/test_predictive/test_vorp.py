"""
Unit tests for VORP calculation, replacement baselines, and surplus ratios (Phase 4C).
"""

import pytest
from src.predictive.config import FORMAT_CONFIGS
from src.predictive.vorp import calculate_player_vorp, compute_pool_surplus_ratio


def test_vorp_replacement_baselines():
    """Verify format-specific empirical P10 replacement levels are correctly configured."""
    t20_cfg = FORMAT_CONFIGS["T20"]
    odi_cfg = FORMAT_CONFIGS["ODI"]
    test_cfg = FORMAT_CONFIGS["TEST"]
    
    assert t20_cfg.replacement_r_bat == 740.0
    assert odi_cfg.replacement_r_bat == 790.0
    assert test_cfg.replacement_r_bat == 950.0
    
    # Bowling replacement anchored at 1000 across formats
    assert t20_cfg.replacement_r_bowl == 1000.0
    assert odi_cfg.replacement_r_bowl == 1000.0
    assert test_cfg.replacement_r_bowl == 1000.0


def test_sub_replacement_negative_vorp():
    """Verify sub-replacement players receive strictly negative VORP values (no artificial truncation)."""
    sub_rep_res = calculate_player_vorp(
        pre_r_bat=650.0,   # Sub-replacement (below 740)
        pre_rd_bat=100.0,
        pre_r_bowl=900.0,  # Sub-replacement (below 1000)
        pre_rd_bowl=100.0,
        pre_r_field=550.0, # Sub-replacement (below 600)
        pre_rd_field=150.0,
        match_format="T20",
        batting_position=4,
        inferred_role="R6_BOWLING_ALLROUNDER",
    )
    
    assert sub_rep_res["vorp_bat"] < 0.0
    assert sub_rep_res["vorp_bowl"] < 0.0
    assert sub_rep_res["vorp_total"] < 0.0
    assert sub_rep_res["is_above_replacement"] is False


def test_elite_positive_vorp():
    """Verify elite player achieves significant positive VORP."""
    elite_res = calculate_player_vorp(
        pre_r_bat=1400.0,
        pre_rd_bat=45.0,
        pre_r_bowl=1350.0,
        pre_rd_bowl=50.0,
        pre_r_field=750.0,
        pre_rd_field=150.0,
        match_format="ODI",
        batting_position=3,
        inferred_role="R5_BATTING_ALLROUNDER",
    )
    
    assert elite_res["vorp_bat"] > 0.0
    assert elite_res["vorp_bowl"] > 0.0
    assert elite_res["vorp_total"] > 0.0
    assert elite_res["is_above_replacement"] is True


def test_pool_surplus_ratio_calculation():
    """Verify surplus ratio calculation across a player cohort."""
    vorps = [15.0, 10.0, 5.0, -2.0, -3.0]
    # Positive sum = 30.0, total abs = 35.0 => ratio = 30 / 35 = 0.857
    ratio = compute_pool_surplus_ratio(vorps)
    assert ratio == 0.857
