"""
CricEngine AI — Benchmark Baseline Models & Comparative Evaluator (Phase 4C)

Benchmarking suite comparing:
1. BM-0: Global / Format Mean
2. BM-1: 10-match Rolling Average (strictly window_size == 10)
3. BM-2: 365-day EWMA Baseline (strictly window_days == 365)
4. BM-3: Exposure-adjusted Empirical Rate Baseline (balls faced * rolling strike rate)
5. Model 4C: CA-HBSS Calibrated Two-Stage Predictive Model

Strictly prevents Cartesian join inflation by enforcing single-window filters.
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.predictive.uncertainty import (
    compute_winkler_score,
    compute_discrete_crps,
    compute_total_variance,
    compute_prediction_intervals,
)


def compute_spearman_rho(x: np.ndarray, y: np.ndarray) -> float:
    """Compute Spearman rank correlation using pure pandas rank Pearson."""
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return 0.0
    rx = pd.Series(x).rank()
    ry = pd.Series(y).rank()
    corr = rx.corr(ry)
    return 0.0 if pd.isna(corr) else float(corr)


def compute_kendall_tau(x: np.ndarray, y: np.ndarray, max_samples: int = 1500) -> float:
    """Compute Kendall's tau via concordant/discordant pair comparison."""
    n = len(x)
    if n < 3:
        return 0.0
    # Subsample if large to guarantee O(1) memory and fast execution
    if n > max_samples:
        indices = np.random.RandomState(42).choice(n, size=max_samples, replace=False)
        a = np.asarray(x)[indices]
        b = np.asarray(y)[indices]
        n = max_samples
    else:
        a = np.asarray(x)
        b = np.asarray(y)

    diff_a = np.sign(a[:, None] - a[None, :])
    diff_b = np.sign(b[:, None] - b[None, :])
    i_upper = np.triu_indices(n, k=1)
    concordant = np.sum(diff_a[i_upper] * diff_b[i_upper])
    total_pairs = n * (n - 1) / 2.0
    if total_pairs <= 0:
        return 0.0
    return float(concordant / total_pairs)


def compute_regression_metrics(
    actuals: np.ndarray,
    predictions: np.ndarray,
    intervals_90: Optional[List[Tuple[float, float]]] = None,
    total_variances: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    Compute comprehensive accuracy, ranking, and probabilistic metrics.
    """
    act = np.asarray(actuals, dtype=float)
    pred = np.asarray(predictions, dtype=float)
    
    n = len(act)
    if n == 0:
        return {
            "n_samples": 0, "mae": 0.0, "rmse": 0.0,
            "pearson_r": 0.0, "spearman_rho": 0.0, "kendall_tau": 0.0,
            "winkler_90": 0.0, "crps": 0.0,
        }

    residuals = act - pred
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    
    # Pearson r
    if np.var(pred) > 1e-9 and np.var(act) > 1e-9:
        p_corr = float(np.corrcoef(pred, act)[0, 1])
        pearson_r = 0.0 if np.isnan(p_corr) else p_corr
    else:
        pearson_r = 0.0

    spearman_rho = compute_spearman_rho(pred, act)
    kendall_tau = compute_kendall_tau(pred, act)

    # Probabilistic metrics
    winkler_scores = []
    crps_scores = []

    # If intervals and variances not provided, estimate them using default overdispersion
    if intervals_90 is None:
        intervals_90 = []
        for p in pred:
            var = p + 0.25 * (p ** 2)
            ints = compute_prediction_intervals(p, var)
            intervals_90.append(ints["interval_90"])

    for y, (l, u) in zip(act, intervals_90):
        winkler_scores.append(compute_winkler_score(l, u, y, nominal_coverage=0.90))

    mean_winkler = float(np.mean(winkler_scores)) if winkler_scores else 0.0

    # Subsample CRPS calculation for speed if n is large
    crps_sample_size = min(500, n)
    crps_indices = np.random.RandomState(42).choice(n, size=crps_sample_size, replace=False) if n > 500 else range(n)
    
    for idx in crps_indices:
        p_val = pred[idx]
        y_val = act[idx]
        v_val = total_variances[idx] if total_variances is not None else (p_val + 0.25 * p_val ** 2)
        crps_scores.append(compute_discrete_crps(p_val, v_val, y_val))

    mean_crps = float(np.mean(crps_scores)) if crps_scores else 0.0

    return {
        "n_samples": n,
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "pearson_r": round(pearson_r, 4),
        "spearman_rho": round(spearman_rho, 4),
        "kendall_tau": round(kendall_tau, 4),
        "winkler_90": round(mean_winkler, 2),
        "crps": round(mean_crps, 2),
    }
