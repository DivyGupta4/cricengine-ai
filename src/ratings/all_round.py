"""
CricEngine AI — All-Round Rating & Value Over Replacement Player (VORP) (Phase 4B)
"""

from __future__ import annotations
import math
from typing import Tuple

from src.ratings.config import FormatConfig
from src.ratings.state_model import PlayerRatingState


def compute_all_round_and_vorp(
    state: PlayerRatingState,
    batting_load: float,
    bowling_load: float,
    format_config: FormatConfig,
    replacement_level_rating: float = 650.0,
    roster_synergy_weight: float = 0.0,
) -> Tuple[float, float, float]:
    """
    Computes:
      1. All-Round Rating (R_allround): Strictly monotonic additive net value model.
      2. Uncertainty (RD_allround).
      3. Value Over Replacement Player (VORP): In physical Net Runs Added Above Replacement.
         CRITICAL: Negative selection value is preserved (NO zero truncation).
      4. RosterSynergyBonus is initially set strictly to 0.0 per Phase 4B mandate.
    """
    # Safe bounds on loads [0, 1]
    b_load = max(0.0, min(1.0, batting_load))
    w_load = max(0.0, min(1.0, bowling_load))

    # 1. Marginal Ability Over Replacement Level
    # (Unscaled ability difference relative to 15th percentile replacement player)
    diff_bat = state.r_bat - replacement_level_rating
    diff_bowl = state.r_bowl - replacement_level_rating

    # 2. Additive Net Value Components (Load-Weighted)
    net_bat = b_load * diff_bat
    net_bowl = w_load * diff_bowl

    # 3. Roster Synergy Bonus (mandated strictly 0.0 initially)
    synergy_bonus = 0.0
    if roster_synergy_weight > 0.0 and net_bat > 0.0 and net_bowl > 0.0:
        abi = (2.0 * b_load * w_load) / (b_load + w_load + 1e-6)
        synergy_bonus = roster_synergy_weight * math.sqrt(net_bat * net_bowl) * abi

    # 4. All-Round Score (Scaled index, strictly monotonic in both disciplines)
    # A player with only batting or only bowling has net_bowl ~ 0 or net_bat ~ 0.
    raw_ar = net_bat + net_bowl + synergy_bonus
    r_allround = max(0.0, min(1500.0, raw_ar * 1.5))

    # All-Round Uncertainty: propogated from constituent dimensions
    total_load = b_load + w_load
    if total_load > 0.0:
        w_b = b_load / total_load
        w_w = w_load / total_load
        rd_allround = math.sqrt(w_b * (state.rd_bat ** 2) + w_w * (state.rd_bowl ** 2))
    else:
        rd_allround = max(state.rd_bat, state.rd_bowl)

    # 5. VORP in Physical Units: Net Runs Added Above Replacement
    # In T20, 100 rating points above replacement ~ 3.5 net runs/match
    # In ODI, 100 rating points ~ 6.0 net runs/match
    # In Test, 100 rating points ~ 9.0 net runs/match
    scale_factor = 0.035 if format_config.format_code == "T20" else (
        0.060 if format_config.format_code == "ODI" else 0.090
    )

    vorp_bat = net_bat * scale_factor
    vorp_bowl = net_bowl * scale_factor
    vorp_field = (state.r_field - 500.0) * (scale_factor * 0.25)

    # CRITICAL: Preserve negative selection values; do NOT truncate with max(0, ...)
    vorp_total = vorp_bat + vorp_bowl + vorp_field

    # Update state fields
    state.r_allround = round(r_allround, 1)
    state.rd_allround = round(max(35.0, min(350.0, rd_allround)), 1)
    state.vorp_rating = round(vorp_total, 2)

    return r_allround, rd_allround, vorp_total
