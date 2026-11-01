"""
CricEngine AI — Rating Engine Configuration & Hyperparameters (Phase 4B)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any

# Root Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CURATED_DB_PATH = BASE_DIR / "data" / "datalake" / "curated" / "cricengine.duckdb"
FEATURE_STORE_V3B_DIR = BASE_DIR / "data" / "datalake" / "feature_store_v3b"
RATING_STORE_V4_DIR = BASE_DIR / "data" / "datalake" / "rating_store_v4"

# Formats
FORMATS = ("T20", "ODI", "Test")

@dataclass(frozen=True)
class FormatConfig:
    """Format-specific dynamic and observation parameters."""
    format_code: str
    half_life_days: float          # Empirical activity half-life (initial hypothesis)
    diffusion_const: float          # Brownian drift parameter c_F (RD / sqrt(day))
    default_wickets_value: float   # Run equivalent of a wicket V_wicket
    min_balls_for_rate: int        # Minimum balls faced/bowled for meaningful rate
    baseline_scoring_rate: float   # Runs per ball baseline
    baseline_economy_rate: float   # Runs per over baseline
    baseline_hazard_rate: float    # Wickets per ball baseline

test_config = FormatConfig(
    format_code="TEST",
    half_life_days=365.0,
    diffusion_const=0.55,
    default_wickets_value=45.0,
    min_balls_for_rate=24,
    baseline_scoring_rate=0.53,   # ~3.15 RPO
    baseline_economy_rate=3.15,
    baseline_hazard_rate=0.019,   # ~1 wkt per 52.6 balls
)

FORMAT_CONFIGS: Dict[str, FormatConfig] = {
    "T20": FormatConfig(
        format_code="T20",
        half_life_days=90.0,
        diffusion_const=1.25,
        default_wickets_value=10.5,
        min_balls_for_rate=6,
        baseline_scoring_rate=1.35,   # ~8.1 RPO
        baseline_economy_rate=8.10,
        baseline_hazard_rate=0.048,   # ~1 wkt per 20.8 balls
    ),
    "ODI": FormatConfig(
        format_code="ODI",
        half_life_days=180.0,
        diffusion_const=0.85,
        default_wickets_value=30.0,
        min_balls_for_rate=12,
        baseline_scoring_rate=0.88,   # ~5.25 RPO
        baseline_economy_rate=5.25,
        baseline_hazard_rate=0.032,   # ~1 wkt per 31.2 balls
    ),
    "TEST": test_config,
    "Test": test_config,
}

@dataclass
class RatingEngineConfig:
    """Master Rating Engine Configuration."""
    version: str = "4.0.0-phase4b"
    
    # Rating Scale & Normalization (CricEngine native scale)
    native_mean: float = 1000.0
    native_rd_init: float = 350.0
    native_rd_min: float = 35.0
    native_rd_max: float = 350.0
    
    # Laplace Assumed Density Filtering parameters
    max_laplace_iterations: int = 10
    laplace_tolerance: float = 1e-5
    
    # Observation overdispersion parameters (Negative-Binomial phi)
    phi_bat_runs: float = 0.25
    phi_bowl_wickets: float = 0.20
    phi_bowl_econ: float = 0.15
    zip_zero_inflation: float = 0.70
    
    # Venue Bayes Shrinkage
    venue_min_samples: int = 15
    venue_shrinkage_k: float = 10.0
    
    # Replacement level quantile
    replacement_quantile: float = 0.15
    
    # Roster synergy bonus (mandated strictly 0.0 initially by Phase 4B instructions)
    roster_synergy_bonus_weight: float = 0.0
    
    # Babar Ali (c65e0275) discrete mixture decision weight
    probable_identity_mixture_weight: float = 0.65
    
    # Validation Epochs
    burn_in_end: str = "2014-12-31"
    tuning_end: str = "2019-12-31"
    holdout_end: str = "2024-12-31"

DEFAULT_CONFIG = RatingEngineConfig()
