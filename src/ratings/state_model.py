"""
CricEngine AI — Player State Representation & Container (Phase 4B)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import Optional, Dict, Any


@dataclass
class PlayerRatingState:
    """
    Complete probabilistic rating state for a single player in a single format.
    Maintains latent parameters, display indices, and uncertainty estimates.
    """
    player_id: str
    match_format: str
    as_of_date: str
    last_match_date: Optional[str] = None
    observations_count: int = 0
    effective_exposure_bat: float = 0.0
    effective_exposure_bowl: float = 0.0
    effective_exposure_field: float = 0.0
    
    # 1. Latent State Parameters (Log Link Scale)
    # Batting scoring rate: ln(runs / ball)
    theta_bat_rate: float = 0.0
    var_bat_rate: float = 0.25
    
    # Batting survival: logit(survival probability per ball)
    theta_bat_surv: float = 3.20
    var_bat_surv: float = 0.35
    
    # Bowling wicket hazard: ln(wickets / legal ball)
    theta_bowl_haz: float = -3.20
    var_bowl_haz: float = 0.35
    
    # Bowling economy: ln(runs conceded / legal ball)
    theta_bowl_econ: float = 0.0
    var_bowl_econ: float = 0.25
    
    # Fielding hazard: ln(involvements / 1000 team balls)
    theta_field: float = -4.50
    var_field: float = 0.60
    
    # 2. Scaled Display Ratings (Native 1000 Scale)
    r_bat: float = 1000.0
    rd_bat: float = 350.0
    r_bowl: float = 1000.0
    rd_bowl: float = 350.0
    r_field: float = 500.0
    rd_field: float = 350.0
    
    # 3. Composites & Value
    r_allround: float = 0.0
    rd_allround: float = 350.0
    vorp_rating: float = 0.0  # Runs Above Replacement
    
    # 4. Form & Momentum
    recent_form_bat: float = 0.0
    recent_form_bowl: float = 0.0
    
    # 5. Role & Identity Attributes
    inferred_role: str = "R3_MIDDLE_ORDER"
    role_confidence: float = 0.50
    role_uncertainty_flag: Optional[str] = "DEBUTANT_INSUFFICIENT_HISTORY"
    identity_confidence_status: str = "VERIFIED"
    rating_status: str = "DEBUTANT"
    
    def copy(self) -> PlayerRatingState:
        """Deep copy of the rating state."""
        return PlayerRatingState(**self.__dict__)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to serializable dictionary for Parquet storage."""
        return {
            "player_id": self.player_id,
            "match_format": self.match_format,
            "as_of_date": self.as_of_date,
            "last_match_date": self.last_match_date,
            "observations_count": self.observations_count,
            "effective_exposure_bat": round(self.effective_exposure_bat, 2),
            "effective_exposure_bowl": round(self.effective_exposure_bowl, 2),
            "effective_exposure_field": round(self.effective_exposure_field, 2),
            "theta_bat_rate": round(self.theta_bat_rate, 4),
            "var_bat_rate": round(self.var_bat_rate, 4),
            "theta_bat_surv": round(self.theta_bat_surv, 4),
            "var_bat_surv": round(self.var_bat_surv, 4),
            "theta_bowl_haz": round(self.theta_bowl_haz, 4),
            "var_bowl_haz": round(self.var_bowl_haz, 4),
            "theta_bowl_econ": round(self.theta_bowl_econ, 4),
            "var_bowl_econ": round(self.var_bowl_econ, 4),
            "theta_field": round(self.theta_field, 4),
            "var_field": round(self.var_field, 4),
            "r_bat": round(self.r_bat, 1),
            "rd_bat": round(self.rd_bat, 1),
            "r_bowl": round(self.r_bowl, 1),
            "rd_bowl": round(self.rd_bowl, 1),
            "r_field": round(self.r_field, 1),
            "rd_field": round(self.rd_field, 1),
            "r_allround": round(self.r_allround, 1),
            "rd_allround": round(self.rd_allround, 1),
            "vorp_rating": round(self.vorp_rating, 2),
            "recent_form_bat": round(self.recent_form_bat, 3),
            "recent_form_bowl": round(self.recent_form_bowl, 3),
            "inferred_role": self.inferred_role,
            "role_confidence": round(self.role_confidence, 3),
            "role_uncertainty_flag": self.role_uncertainty_flag,
            "identity_confidence_status": self.identity_confidence_status,
            "rating_status": self.rating_status,
        }
    
    @classmethod
    def create_debutant(cls, player_id: str, match_format: str, as_of_date: str, identity_status: str = "VERIFIED") -> PlayerRatingState:
        """Initialize an uninformative debutant prior."""
        return cls(
            player_id=player_id,
            match_format=match_format,
            as_of_date=as_of_date,
            identity_confidence_status=identity_status,
            rating_status="DEBUTANT",
            role_uncertainty_flag="DEBUTANT_INSUFFICIENT_HISTORY",
        )
