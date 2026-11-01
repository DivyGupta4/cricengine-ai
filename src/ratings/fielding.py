"""
CricEngine AI — Fielding Ability State-Space Updates (Phase 4B)
"""

from __future__ import annotations
import math

from src.ratings.config import FormatConfig
from src.ratings.observation_models import laplace_mode_filter_zip
from src.ratings.state_model import PlayerRatingState


def update_fielding_state(
    state: PlayerRatingState,
    catches_taken: int,
    runouts_involved: int,
    in_starting_xi: bool,
    team_balls_fielded: int,
    format_config: FormatConfig,
    pi_zero: float = 0.70,
) -> PlayerRatingState:
    """
    Update fielding ability state conservatively using Zero-Inflated Poisson ADF.
    Preserves Phase 4A.1 safeguards:
      - If not in starting XI, exposure is 0 (no update).
      - Denominator is team deliveries fielded while in the starting XI.
      - Maintains high epistemic uncertainty due to unrecorded non-dismissal opportunities.
    """
    if not in_starting_xi or team_balls_fielded <= 0:
        return state

    # Weight direct-hit run-outs slightly higher (1.5x)
    total_involvements = int(catches_taken + 1.5 * runouts_involved)
    exposure = float(team_balls_fielded)

    # Baseline fielding rate ~ 0.01 per ball (approx 1 catch per 100 balls)
    context_offset = math.log(0.010)

    new_theta_field, new_var_field, conv_field = laplace_mode_filter_zip(
        prior_mean=state.theta_field,
        prior_var=state.var_field,
        observed_c=total_involvements,
        exposure=exposure,
        pi_zero=pi_zero,
        context_offset=context_offset,
    )

    state.theta_field = new_theta_field
    state.var_field = new_var_field
    state.effective_exposure_field += exposure

    # Display rating: centered at 500 (average international fielder)
    z_field = state.theta_field - (-4.50)
    state.r_field = max(100.0, min(950.0, 500.0 + 150.0 * z_field))
    
    # Conservative uncertainty: fielding uncertainty has a higher floor (150.0)
    # reflecting the lack of dropped-catch and ground fielding data
    state.rd_field = max(150.0, min(350.0, 350.0 * math.sqrt(max(0.18, state.var_field))))

    return state
