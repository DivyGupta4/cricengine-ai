"""
CricEngine AI — Law of Total Variance & Predictive Uncertainty Engine (Phase 4C)

Rigorous quantification of predictive uncertainty combining:
1. Aleatoric overdispersion (stochastic match process via Negative Binomial)
2. Epistemic parameter uncertainty (posterior rating uncertainty RD via log-normal link)
"""

from __future__ import annotations
import math
from typing import Dict, Tuple, List, Optional
import numpy as np
import pandas as pd


def compute_total_variance(
    mu_point: float,
    exposure: float,
    beta: float,
    rd: float,
    dispersion_alpha: float = 0.25,
    native_scale: float = 350.0,
) -> Tuple[float, float, float]:
    """
    Apply the Law of Total Variance to compound rate-exposure processes:
        Var_total(Y) = E[Var(Y | theta)] + Var(E[Y | theta])
        
    Args:
        mu_point: Point estimate of expected outcome E[Y]
        exposure: Match exposure (balls faced or legal balls bowled)
        beta: Link sensitivity coefficient
        rd: Rating deviation (epistemic uncertainty on native 1000 scale)
        dispersion_alpha: Negative Binomial overdispersion parameter
        native_scale: Scaling factor for native rating (default 350.0)
        
    Returns:
        (total_variance, aleatoric_variance, epistemic_variance)
    """
    if mu_point <= 0.0 or exposure <= 0.0:
        return 0.0, 0.0, 0.0

    sigma_z = max(0.01, rd / native_scale)
    beta_sq_sigma_sq = (beta * sigma_z) ** 2
    
    # Clip exponent to avoid numerical overflow
    beta_sq_sigma_sq = min(10.0, beta_sq_sigma_sq)
    
    # Epistemic variance: Var(E[Y | theta]) = mu_point^2 * (exp(beta^2 * sigma_z^2) - 1)
    exp_factor = math.expm1(beta_sq_sigma_sq)
    epistemic_var = (mu_point ** 2) * exp_factor
    
    # Aleatoric variance: E[Var(Y | theta)] = mu_point + alpha * E[mu^2]
    # where E[mu^2] = (mu_point)^2 + epistemic_var
    aleatoric_var = mu_point + dispersion_alpha * ((mu_point ** 2) + epistemic_var)
    
    total_var = aleatoric_var + epistemic_var
    return total_var, aleatoric_var, epistemic_var


def compute_negbin_quantiles(
    mu: float,
    total_var: float,
    quantiles: Tuple[float, ...] = (0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975),
) -> Dict[float, float]:
    """
    Compute predictive quantiles from effective compound Negative Binomial distribution.
    Matches mean and total variance.
    """
    if mu <= 0.0:
        return {q: 0.0 for q in quantiles}

    # Ensure variance strictly exceeds mean for Negative Binomial
    eff_var = max(total_var, mu * 1.001)
    
    r = (mu * mu) / (eff_var - mu)
    p = r / (r + mu)
    
    # If r is very large (overdispersion negligible), fall back to normal/poisson approximation
    if r > 1000.0 or p < 1e-6:
        std = math.sqrt(eff_var)
        results = {}
        for q in quantiles:
            # Approximate standard normal quantile
            z = norm_ppf(q)
            results[q] = max(0.0, round(mu + z * std, 1))
        return results

    # Recursive PMF computation for exact discrete quantiles
    prob_0 = math.pow(p, r) if p > 0.0 else 0.0
    cdf = prob_0
    prob_k = prob_0
    k = 0
    results = {}
    sorted_q = sorted(quantiles)
    q_idx = 0
    max_k = int(max(150, mu + 8.0 * math.sqrt(eff_var)))

    while q_idx < len(sorted_q) and k <= max_k:
        target_q = sorted_q[q_idx]
        if cdf >= target_q:
            results[target_q] = float(k)
            q_idx += 1
            continue
        k += 1
        prob_k = prob_k * ((k - 1 + r) / k) * (1.0 - p)
        cdf += prob_k

    while q_idx < len(sorted_q):
        results[sorted_q[q_idx]] = float(k)
        q_idx += 1

    return results


def compute_prediction_intervals(
    mu: float,
    total_var: float,
) -> Dict[str, Tuple[float, float]]:
    """
    Compute standard 50%, 80%, 90%, and 95% central prediction intervals.
    
    Returns:
        dict: {
            "interval_50": (p25, p75),
            "interval_80": (p10, p90),
            "interval_90": (p05, p95),
            "interval_95": (p025, p975),
        }
    """
    q_dict = compute_negbin_quantiles(
        mu,
        total_var,
        quantiles=(0.025, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.975),
    )
    return {
        "interval_50": (q_dict[0.25], q_dict[0.75]),
        "interval_80": (q_dict[0.10], q_dict[0.90]),
        "interval_90": (q_dict[0.05], q_dict[0.95]),
        "interval_95": (q_dict[0.025], q_dict[0.975]),
    }


def compute_winkler_score(
    lower: float,
    upper: float,
    actual: float,
    nominal_coverage: float,
) -> float:
    """
    Continuous interval score (Winkler Score):
        IS_alpha(L, U, y) = (U - L) + (2 / alpha) * (L - y) * 1(y < L) + (2 / alpha) * (y - U) * 1(y > U)
    where alpha = 1.0 - nominal_coverage.
    Lower score is better.
    """
    alpha = 1.0 - nominal_coverage
    width = upper - lower
    penalty = 0.0
    if actual < lower:
        penalty = (2.0 / alpha) * (lower - actual)
    elif actual > upper:
        penalty = (2.0 / alpha) * (actual - upper)
    return width + penalty


def compute_discrete_crps(
    mu: float,
    total_var: float,
    actual: float,
    max_k: Optional[int] = None,
) -> float:
    """
    Continuous Ranked Probability Score (CRPS) for discrete count distribution:
        CRPS(F, y) = sum_{k=0}^{K} (F(k) - 1(k >= y))^2
    """
    if mu <= 0.0:
        return abs(actual)

    eff_var = max(total_var, mu * 1.001)
    r = (mu * mu) / (eff_var - mu)
    p = r / (r + mu)
    
    if max_k is None:
        max_k = int(max(actual + 20, mu + 5.0 * math.sqrt(eff_var)))

    prob_0 = math.pow(p, r) if p > 0.0 else 0.0
    cdf = prob_0
    prob_k = prob_0
    crps = 0.0

    for k in range(max_k + 1):
        indicator = 1.0 if k >= actual else 0.0
        crps += (cdf - indicator) ** 2
        
        # Next term
        if k < max_k:
            prob_k = prob_k * ((k + r) / (k + 1)) * (1.0 - p)
            cdf = min(1.0, cdf + prob_k)

    return crps


def norm_ppf(p: float) -> float:
    """Rational approximation of standard normal inverse CDF (Beasley-Springer-Moro)."""
    if p <= 0.0:
        return -5.0
    if p >= 1.0:
        return 5.0
    if p == 0.5:
        return 0.0
        
    a = [
        -3.969683028665376e+01,  2.209460984245205e+02,
        -2.759285104469687e+02,  1.383577518672690e+02,
        -3.066479806614716e+01,  2.506628277459239e+00
    ]
    b = [
        -5.447609879822406e+01,  1.615858368580409e+02,
        -1.556989798598866e+02,  6.680131188771972e+01,
        -1.328068155288572e+01
    ]
    c = [
        -7.784894002430293e-03, -3.223964580411365e-01,
        -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00,  2.938163982698783e+00
    ]
    d = [
         7.784695709041462e-03,  3.224671290700398e-01,
         2.445134137142996e+00,  3.754408661907416e+00
    ]
    
    p_low = 0.02425
    p_high = 1.0 - p_low
    
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    elif p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    else:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)
