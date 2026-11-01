"""
CricEngine AI — Temporal Dynamics & Continuous-Time Variance Inflation (Phase 4B)
"""

from __future__ import annotations
import math
from datetime import datetime
from typing import Optional

from src.ratings.config import FormatConfig
from src.ratings.state_model import PlayerRatingState


def parse_date(date_val: Any) -> datetime:
    """Robust ISO date parsing."""
    if isinstance(date_val, datetime):
        return date_val
    if hasattr(date_val, "strftime"):
        return datetime.strptime(date_val.strftime("%Y-%m-%d"), "%Y-%m-%d")
    s = str(date_val)[:10]
    return datetime.strptime(s, "%Y-%m-%d")


def apply_temporal_drift(
    state: PlayerRatingState,
    current_match_date: Any,
    format_config: FormatConfig,
    rd_max: float = 350.0,
) -> PlayerRatingState:
    """
    Applies continuous-time Brownian variance inflation during calendar inactivity:
      RD'(t) = min(sqrt(RD^2 + c_F^2 * dt), RD_max)
    Latent mean abilities remain constant; only epistemic uncertainty increases.
    """
    date_str = str(current_match_date)[:10]
    if state.last_match_date is None:
        state.last_match_date = date_str
        state.as_of_date = date_str
        return state

    d_last = parse_date(state.last_match_date)
    d_curr = parse_date(current_match_date)
    dt_days = max(0.0, (d_curr - d_last).total_seconds() / 86400.0)

    if dt_days <= 0.0:
        state.as_of_date = current_match_date
        return state

    # 1. Brownian variance inflation on display Rating Deviations (RD)
    c_f = format_config.diffusion_const
    growth = (c_f ** 2) * dt_days

    state.rd_bat = min(rd_max, math.sqrt(state.rd_bat ** 2 + growth))
    state.rd_bowl = min(rd_max, math.sqrt(state.rd_bowl ** 2 + growth))
    state.rd_field = min(rd_max, math.sqrt(state.rd_field ** 2 + growth))

    # 2. Diffusion on latent parameter variances
    q_drift = 0.0005 * dt_days
    state.var_bat_rate = min(0.60, state.var_bat_rate + q_drift)
    state.var_bat_surv = min(0.70, state.var_bat_surv + q_drift)
    state.var_bowl_haz = min(0.70, state.var_bowl_haz + q_drift)
    state.var_bowl_econ = min(0.60, state.var_bowl_econ + q_drift)
    state.var_field = min(1.00, state.var_field + q_drift)

    # 3. Form decay (Recent form regresses toward zero with half-life)
    hl = format_config.half_life_days
    decay = math.exp(-0.69315 * dt_days / hl)
    state.recent_form_bat *= decay
    state.recent_form_bowl *= decay

    # 4. Status update
    if dt_days > 365.0:
        state.rating_status = "INACTIVE"
    elif state.observations_count >= 5:
        state.rating_status = "ACTIVE"
    else:
        state.rating_status = "DEBUTANT"

    state.as_of_date = date_str
    return state
