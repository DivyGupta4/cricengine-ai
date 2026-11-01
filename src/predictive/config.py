"""
CricEngine AI — Phase 4C Configuration & Hyperparameters
Integrated Predictive Modelling, Statistical Calibration & VORP Implementation
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Tuple

# Root Directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CURATED_DB_PATH = BASE_DIR / "data" / "datalake" / "curated" / "cricengine.duckdb"
FEATURE_STORE_V3B_DIR = BASE_DIR / "data" / "datalake" / "feature_store_v3b"
RATING_STORE_V4_DIR = BASE_DIR / "data" / "datalake" / "rating_store_v4"
PREDICTIVE_STORE_V4C_DIR = BASE_DIR / "data" / "datalake" / "predictive_store_v4c"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis" / "phase_4c"
DOCS_DIR = BASE_DIR / "docs" / "phase_4c"

# Formats
FORMATS = ("T20", "ODI", "TEST")


@dataclass(frozen=True)
class PredictiveFormatConfig:
    """Format-specific predictive baselines, exposure priors, and valuation weights."""
    format_code: str
    baseline_scoring_rate: float      # Baseline runs per ball (lambda_0)
    baseline_economy_rate: float      # Baseline runs per over (e_0)
    baseline_hazard_rate: float       # Baseline wickets per legal ball (h_0)
    wicket_run_value: float           # Run equivalence of a wicket (V_wkt)
    catch_run_value: float            # Run equivalence of a catch/dismissal involvement
    
    # Replacement level ratings (empirical active P10)
    replacement_r_bat: float
    replacement_r_bowl: float
    replacement_r_field: float
    
    # Expected balls faced by batting position (1 to 11)
    position_balls_faced: Dict[int, float]
    
    # Expected legal balls bowled by inferred role
    role_balls_bowled: Dict[str, float]


# Format Baseline Definitions
FORMAT_CONFIGS: Dict[str, PredictiveFormatConfig] = {
    "T20": PredictiveFormatConfig(
        format_code="T20",
        baseline_scoring_rate=1.35,     # ~8.10 RPO
        baseline_economy_rate=8.10,     # 1.35 runs/ball
        baseline_hazard_rate=0.048,     # 1 wicket per ~20.8 balls
        wicket_run_value=10.5,
        catch_run_value=3.5,
        replacement_r_bat=740.0,
        replacement_r_bowl=1000.0,
        replacement_r_field=600.0,
        position_balls_faced={
            1: 26.5, 2: 26.5, 3: 20.0, 4: 16.0, 5: 12.0,
            6: 9.0, 7: 6.5, 8: 4.5, 9: 3.0, 10: 2.0, 11: 1.5,
        },
        role_balls_bowled={
            "R8_PACE_SPECIALIST": 22.0,
            "R7_SPIN_SPECIALIST": 22.0,
            "R6_BOWLING_ALLROUNDER": 18.0,
            "R5_BATTING_ALLROUNDER": 8.0,
            "R4_WICKETKEEPER": 0.0,
            "R3_MIDDLE_ORDER": 1.5,
            "R2_TOP_ORDER": 0.5,
            "R1_OPENER": 0.2,
        },
    ),
    "ODI": PredictiveFormatConfig(
        format_code="ODI",
        baseline_scoring_rate=0.88,     # ~5.28 RPO
        baseline_economy_rate=5.25,     # 0.875 runs/ball
        baseline_hazard_rate=0.032,     # 1 wicket per ~31.2 balls
        wicket_run_value=30.0,
        catch_run_value=7.0,
        replacement_r_bat=790.0,
        replacement_r_bowl=1000.0,
        replacement_r_field=625.0,
        position_balls_faced={
            1: 62.0, 2: 62.0, 3: 48.0, 4: 40.0, 5: 32.0,
            6: 24.0, 7: 18.0, 8: 12.0, 9: 8.0, 10: 5.0, 11: 3.0,
        },
        role_balls_bowled={
            "R8_PACE_SPECIALIST": 52.0,
            "R7_SPIN_SPECIALIST": 52.0,
            "R6_BOWLING_ALLROUNDER": 42.0,
            "R5_BATTING_ALLROUNDER": 18.0,
            "R4_WICKETKEEPER": 0.0,
            "R3_MIDDLE_ORDER": 3.0,
            "R2_TOP_ORDER": 1.0,
            "R1_OPENER": 0.5,
        },
    ),
    "TEST": PredictiveFormatConfig(
        format_code="TEST",
        baseline_scoring_rate=0.53,     # ~3.18 RPO
        baseline_economy_rate=3.15,     # 0.525 runs/ball
        baseline_hazard_rate=0.019,     # 1 wicket per ~52.6 balls
        wicket_run_value=45.0,
        catch_run_value=10.0,
        replacement_r_bat=950.0,
        replacement_r_bowl=1000.0,
        replacement_r_field=720.0,
        position_balls_faced={
            1: 85.0, 2: 85.0, 3: 80.0, 4: 75.0, 5: 65.0,
            6: 52.0, 7: 42.0, 8: 30.0, 9: 18.0, 10: 12.0, 11: 8.0,
        },
        role_balls_bowled={
            "R8_PACE_SPECIALIST": 110.0,
            "R7_SPIN_SPECIALIST": 110.0,
            "R6_BOWLING_ALLROUNDER": 80.0,
            "R5_BATTING_ALLROUNDER": 35.0,
            "R4_WICKETKEEPER": 0.0,
            "R3_MIDDLE_ORDER": 6.0,
            "R2_TOP_ORDER": 2.0,
            "R1_OPENER": 1.0,
        },
    ),
}
# Alias for "Test"
FORMAT_CONFIGS["Test"] = FORMAT_CONFIGS["TEST"]


@dataclass
class PredictiveEngineConfig:
    """Master Predictive and Calibration Configuration."""
    version: str = "4.3.0-phase4c"
    
    # Latent Scaling & Standardization
    native_mean: float = 1000.0
    native_scale: float = 350.0
    field_native_mean: float = 500.0
    
    # Tempered Sensitivity Coefficients (Calibrated GLM Link Scales)
    beta_bat_rate: float = 0.18
    beta_bowl_haz: float = 0.16
    beta_bowl_econ: float = 0.12
    beta_field_inv: float = 0.10
    
    # Aleatoric Overdispersion Parameters (Negative Binomial alpha)
    dispersion_bat_runs: float = 0.25
    dispersion_bowl_wickets: float = 0.20
    dispersion_bowl_runs: float = 0.15
    
    # Context Sensitivity Powers
    park_factor_power_bat: float = 1.00
    opp_bowling_power_bat: float = 1.00
    park_factor_power_bowl: float = 0.45
    opp_batting_power_bowl: float = 1.00
    
    # Epistemic Uncertainty Floors
    min_rd_floor_bat: float = 35.0
    min_rd_floor_bowl: float = 35.0
    min_rd_floor_field: float = 150.0
    
    # Prediction Intervals Evaluated
    prediction_quantiles: Tuple[float, ...] = (0.50, 0.80, 0.90, 0.95)
    
    # VORP Minimum Matches for Experience Filtering
    vorp_min_matches_experienced: int = 5
    
    # Temporal Split Boundaries (Strict D-1)
    train_end_date: str = "2019-12-31"
    validation_start_date: str = "2020-01-01"
    validation_end_date: str = "2023-12-31"
    holdout_start_date: str = "2024-01-01"
    holdout_end_date: str = "2026-12-31"
