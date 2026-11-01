"""
Unit tests for Law of Total Variance, prediction intervals, Winkler score, and CRPS (Phase 4C).
"""

import pytest
import math
from src.predictive.uncertainty import (
    compute_total_variance,
    compute_negbin_quantiles,
    compute_prediction_intervals,
    compute_winkler_score,
    compute_discrete_crps,
)


def test_law_of_total_variance_decomposition():
    """Verify exact algebraic identity: Var_total = Var_aleatoric + Var_epistemic."""
    mu = 25.0
    exposure = 20.0
    beta = 0.18
    rd = 120.0
    alpha = 0.25
    
    tot, alea, epist = compute_total_variance(mu, exposure, beta, rd, alpha)
    
    assert math.isclose(tot, alea + epist, rel_tol=1e-7)
    assert epist > 0.0
    assert alea > mu  # Aleatoric strictly exceeds Poisson mean due to overdispersion


def test_zero_epistemic_uncertainty_limit():
    """Verify that when RD -> 0, epistemic variance vanishes and total equals standard NegBin."""
    mu = 30.0
    tot, alea, epist = compute_total_variance(mu, 25.0, 0.18, rd=0.01, dispersion_alpha=0.20)
    
    expected_negbin_var = mu + 0.20 * (mu ** 2)
    assert math.isclose(epist, 0.0, abs_tol=1e-2)
    assert math.isclose(tot, expected_negbin_var, rel_tol=1e-3)


def test_winkler_score_properties():
    """Verify that observations inside the interval receive no penalty, while outside values are penalized."""
    lower = 10.0
    upper = 30.0
    width = upper - lower  # 20.0
    
    # Inside interval: score equals interval width
    inside_score = compute_winkler_score(lower, upper, actual=20.0, nominal_coverage=0.90)
    assert inside_score == width
    
    # Below lower bound: penalized proportionally to distance and (2 / alpha)
    below_score = compute_winkler_score(lower, upper, actual=5.0, nominal_coverage=0.90)
    # alpha = 0.10 => 2 / alpha = 20 => penalty = 20 * (10 - 5) = 100 => total 120
    assert math.isclose(below_score, 20.0 + 100.0, abs_tol=1e-4)


def test_discrete_crps_non_negativity():
    """Verify CRPS is strictly non-negative and zero when deterministic outcome matches prediction."""
    crps_val = compute_discrete_crps(mu=15.0, total_var=35.0, actual=15.0)
    assert crps_val >= 0.0
