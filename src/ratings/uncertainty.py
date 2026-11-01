"""
CricEngine AI — Bayesian Uncertainty & Credible Intervals (Phase 4B)
"""

from __future__ import annotations
import math
from typing import Tuple


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (Phi)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_credible_interval(mean: float, rd: float, alpha: float = 0.10) -> Tuple[float, float]:
    """
    Computes symmetric Bayesian credible interval.
    alpha = 0.10 -> 90% interval (z = 1.6449)
    alpha = 0.05 -> 95% interval (z = 1.95996)
    """
    z = 1.644853 if abs(alpha - 0.10) < 0.01 else 1.959964
    lower = mean - z * rd
    upper = mean + z * rd
    return lower, upper


def probability_player_superiority(mean_a: float, rd_a: float, mean_b: float, rd_b: float) -> float:
    """
    Computes exact Bayesian probability P(theta_A > theta_B | Data).
    Delta ~ N(mean_a - mean_b, rd_a^2 + rd_b^2)
    """
    diff = mean_a - mean_b
    sigma_diff = math.sqrt(rd_a ** 2 + rd_b ** 2)
    if sigma_diff <= 0.0:
        return 0.5 if diff == 0.0 else (1.0 if diff > 0.0 else 0.0)
    z = diff / sigma_diff
    return normal_cdf(z)


def risk_adjusted_selection_value(mean: float, rd: float, risk_aversion: float = 0.50) -> float:
    """
    Conservative lower-credible bound for knockout match selection:
    Value = Mean - lambda * RD
    """
    return mean - risk_aversion * rd
