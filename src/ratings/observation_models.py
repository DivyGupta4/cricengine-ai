"""
CricEngine AI — Non-Gaussian Observation Models & Laplace Assumed Density Filtering
"""

from __future__ import annotations
import math
from typing import Tuple, Optional


def laplace_mode_filter_negbin(
    prior_mean: float,
    prior_var: float,
    observed_y: float,
    exposure: float,
    context_offset: float = 0.0,
    phi: float = 0.20,
    max_iter: int = 10,
    tol: float = 1e-5,
) -> Tuple[float, float, bool]:
    """
    Laplace Assumed Density Filter for Negative-Binomial observation with exposure.
    
    y ~ NegBin(mean = exposure * exp(theta + context_offset), dispersion = phi)
    theta ~ N(prior_mean, prior_var)
    
    Returns:
        (posterior_mean, posterior_var, converged_flag)
    """
    if exposure <= 0.0:
        return prior_mean, prior_var, True

    # Initial guess at prior mean
    theta = prior_mean
    converged = False

    for _ in range(max_iter):
        # Clip theta to avoid numerical overflow in exp()
        theta_clipped = max(-15.0, min(15.0, theta))
        mu = exposure * math.exp(theta_clipped + context_offset)
        
        # First and second derivatives of log-likelihood
        denom = 1.0 + phi * mu
        d_ll = (observed_y - mu) / denom
        d2_ll = - (mu * (1.0 + phi * observed_y)) / (denom * denom)
        
        # Penalized objective (Laplace posterior)
        diff = theta - prior_mean
        g_prime = d_ll - diff / prior_var
        g_double_prime = d2_ll - 1.0 / prior_var
        
        # Guard against zero or positive curvature
        if g_double_prime >= -1e-12:
            g_double_prime = -1.0 / prior_var
            
        step = g_prime / g_double_prime
        theta_new = theta - step
        
        if abs(step) < tol:
            theta = theta_new
            converged = True
            break
            
        theta = theta_new

    # Final posterior variance from negative inverse Hessian at mode
    theta_clipped = max(-15.0, min(15.0, theta))
    mu = exposure * math.exp(theta_clipped + context_offset)
    denom = 1.0 + phi * mu
    d2_ll = - (mu * (1.0 + phi * observed_y)) / (denom * denom)
    hessian = d2_ll - 1.0 / prior_var
    post_var = -1.0 / hessian

    # Numerical safeguards
    if not math.isfinite(theta) or not math.isfinite(post_var) or post_var <= 0.0:
        return prior_mean, prior_var, False

    # Variance must strictly decrease or stay bounded
    post_var = min(post_var, prior_var)
    return theta, post_var, converged


def laplace_mode_filter_survival(
    prior_mean: float,
    prior_var: float,
    is_dismissed: bool,
    balls_faced: int,
    context_offset: float = 0.0,
    max_iter: int = 10,
    tol: float = 1e-5,
) -> Tuple[float, float, bool]:
    """
    Laplace Assumed Density Filter for Batting Survival (Balls Per Dismissal).
    
    Hazard per ball: logit(1 - p_out) = theta + context_offset.
    Survival prob per ball: p_surv = sigma(theta + offset)
    Dismissal: D in {0, 1}.
    
    Returns:
        (posterior_mean, posterior_var, converged_flag)
    """
    if balls_faced <= 0:
        return prior_mean, prior_var, True

    d = 1.0 if is_dismissed else 0.0
    b = float(balls_faced)
    theta = prior_mean
    converged = False

    for _ in range(max_iter):
        x = max(-15.0, min(15.0, theta + context_offset))
        # Logistic sigmoid: p_surv
        p_surv = 1.0 / (1.0 + math.exp(-x))
        p_out = 1.0 - p_surv
        
        # d_ll / d_theta
        # ll = (b - d) ln(p_surv) + d ln(p_out)
        d_ll = b * p_out - d
        d2_ll = -b * p_surv * p_out
        
        diff = theta - prior_mean
        g_prime = d_ll - diff / prior_var
        g_double_prime = d2_ll - 1.0 / prior_var
        
        if g_double_prime >= -1e-12:
            g_double_prime = -1.0 / prior_var
            
        step = g_prime / g_double_prime
        theta_new = theta - step
        
        if abs(step) < tol:
            theta = theta_new
            converged = True
            break
            
        theta = theta_new

    x = max(-15.0, min(15.0, theta + context_offset))
    p_surv = 1.0 / (1.0 + math.exp(-x))
    p_out = 1.0 - p_surv
    d2_ll = -b * p_surv * p_out
    hessian = d2_ll - 1.0 / prior_var
    post_var = -1.0 / hessian

    if not math.isfinite(theta) or not math.isfinite(post_var) or post_var <= 0.0:
        return prior_mean, prior_var, False

    post_var = min(post_var, prior_var)
    return theta, post_var, converged


def laplace_mode_filter_zip(
    prior_mean: float,
    prior_var: float,
    observed_c: int,
    exposure: float,
    pi_zero: float = 0.70,
    context_offset: float = 0.0,
    max_iter: int = 10,
    tol: float = 1e-5,
) -> Tuple[float, float, bool]:
    """
    Laplace Assumed Density Filter for Zero-Inflated Poisson fielding dismissals.
    
    c ~ ZIP(pi_zero, lambda = exposure * exp(theta + offset))
    
    Returns:
        (posterior_mean, posterior_var, converged_flag)
    """
    if exposure <= 0.0:
        return prior_mean, prior_var, True

    c = float(observed_c)
    theta = prior_mean
    converged = False

    for _ in range(max_iter):
        theta_clipped = max(-15.0, min(15.0, theta + context_offset))
        lam = exposure * math.exp(theta_clipped)
        
        if c == 0:
            exp_neg_lam = math.exp(-min(50.0, lam))
            p_zero = pi_zero + (1.0 - pi_zero) * exp_neg_lam
            denom = max(1e-12, p_zero)
            d_ll = - (1.0 - pi_zero) * exp_neg_lam * lam / denom
            d2_ll = - (1.0 - pi_zero) * exp_neg_lam * lam * (pi_zero * (1.0 - lam) + (1.0 - pi_zero) * exp_neg_lam) / (denom * denom)
        else:
            # Poisson log-likelihood gradient
            d_ll = c - lam
            d2_ll = -lam
            
        diff = theta - prior_mean
        g_prime = d_ll - diff / prior_var
        g_double_prime = min(-1e-12, d2_ll - 1.0 / prior_var)
        
        step = g_prime / g_double_prime
        theta_new = theta - step
        
        if abs(step) < tol:
            theta = theta_new
            converged = True
            break
            
        theta = theta_new

    theta_clipped = max(-15.0, min(15.0, theta + context_offset))
    lam = exposure * math.exp(theta_clipped)
    if c == 0:
        exp_neg_lam = math.exp(-min(50.0, lam))
        p_zero = max(1e-12, pi_zero + (1.0 - pi_zero) * exp_neg_lam)
        d2_ll = - (1.0 - pi_zero) * exp_neg_lam * lam / p_zero
    else:
        d2_ll = -lam
    hessian = min(-1e-12, d2_ll - 1.0 / prior_var)
    post_var = -1.0 / hessian

    if not math.isfinite(theta) or not math.isfinite(post_var) or post_var <= 0.0:
        return prior_mean, prior_var, False

    post_var = min(post_var, prior_var)
    return theta, post_var, converged
