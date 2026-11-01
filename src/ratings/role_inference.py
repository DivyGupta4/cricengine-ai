"""
CricEngine AI — Dynamic Point-in-Time Role Inference (DPI-RI) (Phase 4B)
"""

from __future__ import annotations
from typing import Tuple, Optional


def infer_dynamic_role(
    rolling_batting_pos: Optional[float],
    rolling_overs_bowled: Optional[float],
    rolling_stumpings: Optional[float],
    pace_spin_class: Optional[str],
    matches_in_window: int = 0,
) -> Tuple[str, float, Optional[str]]:
    """
    Infers tactical player role strictly using pre-match rolling window data.
    Never uses static career-wide primary_role to prevent future lookahead leakage.
    
    Returns:
        (inferred_role, role_confidence, uncertainty_flag)
    """
    if matches_in_window < 5 or rolling_batting_pos is None:
        return "R3_MIDDLE_ORDER", 0.35, "DEBUTANT_INSUFFICIENT_HISTORY"

    pos = float(rolling_batting_pos)
    overs = float(rolling_overs_bowled) if rolling_overs_bowled is not None else 0.0
    stumpings = float(rolling_stumpings) if rolling_stumpings is not None else 0.0
    is_spin = (str(pace_spin_class).lower() == "spin") if pace_spin_class and str(pace_spin_class) not in ("nan", "None", "<NA>") else False

    # Wicketkeeper detection
    if stumpings >= 0.20 or (pos <= 7.0 and overs == 0.0 and stumpings > 0.05):
        return "R5_WICKETKEEPER", 0.85, None

    # Specialist Bowler detection (High overs, low batting position)
    if overs >= 2.5:
        if pos >= 7.5:
            role = "R9_SPIN_SPECIALIST" if is_spin else "R8_PACE_SPECIALIST"
            return role, 0.90, None
        else:
            # Significant overs and top/middle batting order -> All-Rounder
            role = "R7_SPIN_ALLROUNDER" if is_spin else "R6_PACE_ALLROUNDER"
            return role, 0.85, None

    # Part-time bowling / Batting All-Rounder
    if overs >= 1.5 and pos <= 8.0:
        role = "R7_SPIN_ALLROUNDER" if is_spin else "R6_PACE_ALLROUNDER"
        return role, 0.70, None

    # Specialist Batting taxonomy based on entry position centroid
    if pos <= 2.2:
        return "R1_OPENER", 0.90, None
    elif pos <= 3.4:
        return "R2_TOP_ORDER", 0.85, None
    elif pos <= 5.5:
        return "R3_MIDDLE_ORDER", 0.80, None
    elif pos <= 7.5:
        return "R4_FINISHER", 0.75, None
    else:
        # Lower order non-bowler / tailender
        role = "R9_SPIN_SPECIALIST" if is_spin else "R8_PACE_SPECIALIST"
        return role, 0.50, "LOW_WORKLOAD_TAILENDER"
