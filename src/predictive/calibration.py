"""
CricEngine AI — Statistical Calibration Diagnostics & Reliability Engine (Phase 4C)

Evaluates:
1. Empirical Coverage Rates against Nominal Confidence Levels (50%, 80%, 90%, 95%)
2. Reliability Diagrams & Decile Calibration Slopes/Intercepts
3. Discrete Mid-PIT (Probability Integral Transform) Uniformity Diagnostics
4. Monotonic Recalibration via Pool Adjacent Violators Algorithm (PAVA)
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd


def evaluate_interval_coverage(
    actuals: List[float],
    intervals: List[Tuple[float, float]],
    nominal_rate: float,
) -> Dict[str, float]:
    """
    Compute empirical coverage percentage and error for a set of predictions.
    
    Args:
        actuals: Observed outcome values
        intervals: List of (lower, upper) interval tuples
        nominal_rate: Target nominal coverage (e.g. 0.90 for 90%)
        
    Returns:
        dict: {
            "nominal_rate": nominal_rate,
            "empirical_rate": float,
            "coverage_error": float,
            "n_samples": int,
            "under_covered_count": int,
            "over_covered_count": int,
        }
    """
    n = len(actuals)
    if n == 0:
        return {
            "nominal_rate": nominal_rate,
            "empirical_rate": 0.0,
            "coverage_error": -nominal_rate,
            "n_samples": 0,
            "under_covered_count": 0,
            "over_covered_count": 0,
        }

    inside = 0
    below = 0
    above = 0
    
    for y, (low, high) in zip(actuals, intervals):
        if y < low:
            below += 1
        elif y > high:
            above += 1
        else:
            inside += 1

    emp_rate = inside / float(n)
    return {
        "nominal_rate": round(nominal_rate, 4),
        "empirical_rate": round(emp_rate, 4),
        "coverage_error": round(emp_rate - nominal_rate, 4),
        "n_samples": n,
        "below_lower_count": below,
        "above_upper_count": above,
    }


def compute_calibration_curve(
    predictions: List[float],
    actuals: List[float],
    n_bins: int = 10,
) -> Dict[str, Any]:
    """
    Construct decile reliability diagram data and compute calibration regression parameters.
    Perfect calibration satisfies: intercept = 0.0, slope = 1.0.
    """
    if len(predictions) == 0:
        return {"bins": [], "slope": 0.0, "intercept": 0.0, "r_squared": 0.0}

    df = pd.DataFrame({"pred": predictions, "act": actuals}).sort_values("pred").reset_index(drop=True)
    df["bin"] = pd.qcut(df["pred"], q=n_bins, labels=False, duplicates="drop")
    
    bin_stats = df.groupby("bin").agg(
        pred_mean=("pred", "mean"),
        act_mean=("act", "mean"),
        count=("act", "count"),
    ).reset_index()

    # Linear fit between predicted mean and actual mean
    x = bin_stats["pred_mean"].to_numpy()
    y = bin_stats["act_mean"].to_numpy()
    
    if len(x) > 1 and np.var(x) > 1e-9:
        slope, intercept = np.polyfit(x, y, deg=1)
        corr = np.corrcoef(x, y)[0, 1]
        r2 = corr ** 2 if not np.isnan(corr) else 0.0
    else:
        slope, intercept, r2 = 1.0, 0.0, 1.0

    bins_list = []
    for _, row in bin_stats.iterrows():
        bins_list.append({
            "bin": int(row["bin"]),
            "pred_mean": round(float(row["pred_mean"]), 2),
            "act_mean": round(float(row["act_mean"]), 2),
            "count": int(row["count"]),
            "residual": round(float(row["act_mean"] - row["pred_mean"]), 2),
        })

    return {
        "bins": bins_list,
        "calibration_slope": round(float(slope), 3),
        "calibration_intercept": round(float(intercept), 3),
        "r_squared": round(float(r2), 3),
    }


def compute_mid_pit(
    mu: float,
    total_var: float,
    actual: float,
) -> float:
    """
    Compute discrete mid-PIT (Probability Integral Transform) value:
        mid-PIT = F(y - 1) + 0.5 * P(Y = y)
    Under a well-calibrated forecast distribution, mid-PIT is approximately Uniform(0, 1).
    """
    if mu <= 0.0:
        return 0.5

    eff_var = max(total_var, mu * 1.001)
    r = (mu * mu) / (eff_var - mu)
    p = r / (r + mu)
    
    act_int = int(round(actual))
    if act_int < 0:
        return 0.0

    prob_0 = math.pow(p, r) if p > 0.0 else 0.0
    cdf_prev = 0.0
    prob_k = prob_0
    
    for k in range(act_int + 1):
        if k == act_int:
            return round(min(1.0, max(0.0, cdf_prev + 0.5 * prob_k)), 4)
        cdf_prev += prob_k
        prob_k = prob_k * ((k + r) / (k + 1)) * (1.0 - p)

    return 0.5


def fit_isotonic_regression(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Fit monotonic non-decreasing step function via Pool Adjacent Violators Algorithm (PAVA).
    Returns (sorted_x_knots, fitted_y_knots).
    """
    order = np.argsort(x)
    x_sorted = x[order].astype(float)
    y_sorted = y[order].astype(float)
    w = np.ones_like(y_sorted, dtype=float)

    n = len(y_sorted)
    v_y = y_sorted.copy()
    v_w = w.copy()
    v_x = x_sorted.copy()

    i = 0
    while i < n - 1:
        if v_y[i] > v_y[i + 1]:
            new_w = v_w[i] + v_w[i + 1]
            new_y = (v_y[i] * v_w[i] + v_y[i + 1] * v_w[i + 1]) / new_w
            v_y[i] = new_y
            v_w[i] = new_w
            v_y = np.delete(v_y, i + 1)
            v_w = np.delete(v_w, i + 1)
            v_x = np.delete(v_x, i + 1)
            n -= 1
            if i > 0:
                i -= 1
        else:
            i += 1

    return v_x, v_y
