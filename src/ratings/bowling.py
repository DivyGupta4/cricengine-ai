"""
CricEngine AI — Bowling Ability State-Space Updates (Phase 4B)
"""

from __future__ import annotations
import math

from src.ratings.config import FormatConfig
from src.ratings.observation_models import laplace_mode_filter_negbin
from src.ratings.state_model import PlayerRatingState


def update_bowling_state(
    state: PlayerRatingState,
    wickets_taken: int,
    runs_conceded: int,
    legal_balls_bowled: int,
    park_factor: float,
    opp_batting_quality: float,
    format_config: FormatConfig,
    phi_wkt: float = 0.20,
    phi_econ: float = 0.15,
) -> PlayerRatingState:
    """
    Update bowling ability states (wicket hazard & economy containment) using Laplace ADF.
    Strictly adheres to Phase 4A.1:
      - Strong batting opposition (I_BatQuality > 1.0) increases expected runs conceded.
      - Strong batting opposition reduces expected wickets.
    """
    if legal_balls_bowled <= 0:
        return state

    pf = max(0.60, min(1.60, park_factor))
    obq = max(0.50, min(2.50, opp_batting_quality))
    balls = float(legal_balls_bowled)

    # 1. Wicket Hazard Update (Negative-Binomial count with legal balls exposure)
    # Expected wickets = balls * baseline_hazard * (1 / pf^0.45) * (1 / obq)
    base_hazard = format_config.baseline_hazard_rate
    context_offset_haz = math.log(base_hazard) - 0.45 * math.log(pf) - math.log(obq)

    new_theta_haz, new_var_haz, conv_haz = laplace_mode_filter_negbin(
        prior_mean=state.theta_bowl_haz,
        prior_var=state.var_bowl_haz,
        observed_y=float(wickets_taken),
        exposure=balls,
        context_offset=context_offset_haz,
        phi=phi_wkt,
    )

    # 2. Economy Containment Update (Negative-Binomial on runs conceded)
    # Expected runs = balls * (baseline_econ / 6) * pf * obq
    base_econ_per_ball = format_config.baseline_economy_rate / 6.0
    context_offset_econ = math.log(base_econ_per_ball) + math.log(pf) + math.log(obq)

    new_theta_econ, new_var_econ, conv_econ = laplace_mode_filter_negbin(
        prior_mean=state.theta_bowl_econ,
        prior_var=state.var_bowl_econ,
        observed_y=float(runs_conceded),
        exposure=balls,
        context_offset=context_offset_econ,
        phi=phi_econ,
    )

    # Apply updates
    state.theta_bowl_haz = new_theta_haz
    state.var_bowl_haz = new_var_haz
    state.theta_bowl_econ = new_theta_econ
    state.var_bowl_econ = new_var_econ
    state.effective_exposure_bowl += balls

    # 3. Scaled Native Display Index Mapping (1000 scale)
    # Test values wicket taking more (0.60 haz), T20 values economy more (0.55 econ)
    w_haz = 0.45 if format_config.format_code == "T20" else (0.50 if format_config.format_code == "ODI" else 0.60)
    w_econ = 1.0 - w_haz

    # For hazard, higher is better: theta - (-3.20)
    # For economy, LOWER is better: -theta
    haz_residual = state.theta_bowl_haz - (-3.20)
    econ_residual = -state.theta_bowl_econ

    combined_z = w_haz * haz_residual + w_econ * econ_residual
    combined_var = w_haz * state.var_bowl_haz + w_econ * state.var_bowl_econ

    state.r_bowl = max(100.0, min(1900.0, 1000.0 + 350.0 * combined_z))
    state.rd_bowl = max(35.0, min(350.0, 350.0 * math.sqrt(max(0.01, combined_var))))

    # Recent Form update (EWMA residual)
    exp_runs = balls * base_econ_per_ball * pf * obq * math.exp(state.theta_bowl_econ)
    perf_residual = (exp_runs - runs_conceded) / max(6.0, math.sqrt(exp_runs + 1.0))
    state.recent_form_bowl = 0.85 * state.recent_form_bowl + 0.15 * max(-3.0, min(3.0, perf_residual))

    return state
