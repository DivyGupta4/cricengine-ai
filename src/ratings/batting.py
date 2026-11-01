"""
CricEngine AI — Batting Ability State-Space Updates (Phase 4B)
"""

from __future__ import annotations
import math
from typing import Tuple

from src.ratings.config import FormatConfig
from src.ratings.observation_models import (
    laplace_mode_filter_negbin,
    laplace_mode_filter_survival,
)
from src.ratings.state_model import PlayerRatingState


def update_batting_state(
    state: PlayerRatingState,
    runs_scored: int,
    balls_faced: int,
    is_dismissed: bool,
    park_factor: float,
    opp_bowling_quality: float,
    format_config: FormatConfig,
    phi_runs: float = 0.25,
) -> PlayerRatingState:
    """
    Update batting ability states (scoring rate & survival) using Laplace ADF.
    Strictly adheres to Phase 4A.1: tougher bowling (I_OBQ > 1.0) reduces expected runs.
    """
    # Safe bounds on contextual factors
    pf = max(0.60, min(1.60, park_factor))
    obq = max(0.50, min(2.50, opp_bowling_quality))
    
    # If the player did not face any balls, no batting update occurs
    if balls_faced <= 0:
        return state

    # 1. Scoring Rate Update (Negative-Binomial)
    # Expected rate = baseline * pf / obq  ==> offset = ln(baseline) + ln(pf) - ln(obq)
    base_rate = format_config.baseline_scoring_rate
    context_offset_rate = math.log(base_rate) + math.log(pf) - math.log(obq)

    new_theta_rate, new_var_rate, conv_rate = laplace_mode_filter_negbin(
        prior_mean=state.theta_bat_rate,
        prior_var=state.var_bat_rate,
        observed_y=float(runs_scored),
        exposure=float(balls_faced),
        context_offset=context_offset_rate,
        phi=phi_runs,
    )

    # 2. Batting Survival Update (Bernoulli Survival Process)
    # Survival logit offset: tougher attack reduces survival logit (-ln(obq))
    context_offset_surv = 0.45 * math.log(pf) - math.log(obq)

    new_theta_surv, new_var_surv, conv_surv = laplace_mode_filter_survival(
        prior_mean=state.theta_bat_surv,
        prior_var=state.var_bat_surv,
        is_dismissed=is_dismissed,
        balls_faced=balls_faced,
        context_offset=context_offset_surv,
    )

    # Apply updates
    state.theta_bat_rate = new_theta_rate
    state.var_bat_rate = new_var_rate
    state.theta_bat_surv = new_theta_surv
    state.var_bat_surv = new_var_surv
    state.effective_exposure_bat += float(balls_faced)

    # 3. Scaled Native Display Index Mapping (1000 scale)
    # T20 places higher weight on rate (0.75), Test on survival (0.55)
    w_rate = 0.75 if format_config.format_code == "T20" else (0.60 if format_config.format_code == "ODI" else 0.45)
    w_surv = 1.0 - w_rate

    rate_residual = state.theta_bat_rate
    surv_residual = state.theta_bat_surv - 3.20

    combined_z = w_rate * rate_residual + w_surv * surv_residual
    combined_var = w_rate * state.var_bat_rate + w_surv * state.var_bat_surv

    state.r_bat = max(100.0, min(1900.0, 1000.0 + 350.0 * combined_z))
    state.rd_bat = max(35.0, min(350.0, 350.0 * math.sqrt(max(0.01, combined_var))))

    # Recent Form update (EWMA residual)
    exp_runs = balls_faced * base_rate * (pf / obq) * math.exp(state.theta_bat_rate)
    perf_residual = (runs_scored - exp_runs) / max(10.0, math.sqrt(exp_runs + 1.0))
    state.recent_form_bat = 0.85 * state.recent_form_bat + 0.15 * max(-3.0, min(3.0, perf_residual))

    return state
