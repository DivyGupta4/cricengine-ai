"""
CricEngine AI — Step 4B: Feature Definitions, Schema Contracts & Core Formulas

Defines the mathematical formulas, schema contracts, sample cutoffs, format-specific
parameters, and PyArrow types for the CricEngine AI Feature Store.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import pyarrow as pa

# -----------------------------------------------------------------------------
# Architectural Constants & Calibration Parameters
# -----------------------------------------------------------------------------

FORMATS = ["T20", "ODI", "Test"]

COMPETITION_TIERS = {
    1: "INTERNATIONAL",
    2: "IPL",
    3: "SMAT",
}

# Format-Specific Exponential Form Half-Lives (t_1/2 in days)
FORMAT_HALF_LIVES_DAYS: Dict[str, float] = {
    "T20": 90.0,    # High frequency, rapid momentum shifts
    "ODI": 180.0,   # Moderate frequency
    "Test": 365.0,  # Lower match frequency, multi-season technical baseline
}

# Empirical Bayes Shrinkage Strength Parameters (pseudo-counts M)
SHRINKAGE_STRENGTH_BATTING_BALLS = 40.0
SHRINKAGE_STRENGTH_BOWLING_BALLS = 30.0

# Minimum Sample Thresholds for Emitting Rolling Metrics (below cutoff -> NULL)
MIN_SAMPLE_REQUIREMENTS: Dict[str, Dict[str, int]] = {
    "T20": {
        "batting_strike_rate_balls": 30,
        "batting_average_dismissals": 5,
        "bowling_economy_balls": 60,       # 10 overs
        "bowling_strike_rate_wickets": 5,
        "bowling_average_wickets": 5,
        "maiden_overs_count": 10,
        "phase_powerplay_balls": 20,
        "phase_death_balls": 15,
        "fielding_matches": 10,
    },
    "ODI": {
        "batting_strike_rate_balls": 60,
        "batting_average_dismissals": 8,
        "bowling_economy_balls": 120,      # 20 overs
        "bowling_strike_rate_wickets": 8,
        "bowling_average_wickets": 8,
        "maiden_overs_count": 15,
        "phase_powerplay_balls": 30,
        "phase_death_balls": 20,
        "fielding_matches": 10,
    },
    "Test": {
        "batting_strike_rate_balls": 100,
        "batting_average_dismissals": 10,
        "bowling_economy_balls": 180,      # 30 overs
        "bowling_strike_rate_wickets": 10,
        "bowling_average_wickets": 10,
        "maiden_overs_count": 25,
        "phase_powerplay_balls": 50,
        "phase_death_balls": 30,
        "fielding_matches": 8,
    },
}

# Global Format Cohort Priors for Bayesian Shrinkage (Baseline Anchors)
COHORT_PRIORS: Dict[str, Dict[str, float]] = {
    "T20": {
        "batting_strike_rate": 130.0,
        "batting_average": 22.0,
        "bowling_economy_rate": 8.10,
        "bowling_strike_rate": 18.5,
        "bowling_average": 25.0,
    },
    "ODI": {
        "batting_strike_rate": 85.0,
        "batting_average": 31.0,
        "bowling_economy_rate": 5.25,
        "bowling_strike_rate": 36.0,
        "bowling_average": 31.5,
    },
    "Test": {
        "batting_strike_rate": 52.0,
        "batting_average": 32.5,
        "bowling_economy_rate": 3.15,
        "bowling_strike_rate": 62.0,
        "bowling_average": 32.5,
    },
}

# Competition Tier Multipliers
TIER_DISCOUNT_FACTORS = {
    1: 1.00,  # Tier 1: International
    2: 0.92,  # Tier 2: IPL
    3: 0.72,  # Tier 3: SMAT
}

MATCH_WINDOWS = [5, 10, 20]
TIME_WINDOWS_DAYS = [30, 90, 365]


# -----------------------------------------------------------------------------
# Mathematical Core Helper Functions
# -----------------------------------------------------------------------------

def compute_recency_weight(delta_days: float, half_life_days: float) -> float:
    """
    Compute exponential recency decay weight: w = 2^(-delta_days / half_life_days).
    delta_days must be strictly > 0.
    """
    if delta_days <= 0:
        return 1.0
    return math.pow(2.0, -delta_days / half_life_days)


def apply_bayesian_shrinkage(
    observed_mean: Optional[float],
    sample_size: float,
    cohort_prior: float,
    pseudo_counts: float,
) -> Optional[float]:
    """
    Empirical Bayes shrinkage towards cohort prior:
    theta_shrunk = (sample_size / (sample_size + M)) * observed + (M / (sample_size + M)) * prior
    """
    if observed_mean is None or sample_size <= 0:
        return cohort_prior
    weight_obs = sample_size / (sample_size + pseudo_counts)
    weight_prior = pseudo_counts / (sample_size + pseudo_counts)
    return round((weight_obs * observed_mean) + (weight_prior * cohort_prior), 3)


def compute_all_rounder_index(batting_load: float, bowling_load: float) -> float:
    """
    Compute All-Rounder Balance Index (ABI): Harmonic mean of batting and bowling load.
    ABI = 2 * (L_bat * L_bowl) / (L_bat + L_bowl + epsilon)
    """
    if batting_load <= 0.0 or bowling_load <= 0.0:
        return 0.0
    eps = 1e-6
    return round((2.0 * batting_load * bowling_load) / (batting_load + bowling_load + eps), 4)


# -----------------------------------------------------------------------------
# PyArrow Schema Contracts
# -----------------------------------------------------------------------------

PLAYER_MATCH_SCHEMA = pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("competition_name", pa.string()),
    ("competition_tier", pa.int8()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("start_date", pa.date32()),
    ("team_name", pa.string()),
    ("opposition_team", pa.string()),
    ("venue_name", pa.string()),
    ("canonical_venue_name", pa.string()),
    ("city", pa.string()),
    ("participation_role", pa.string()),
    ("in_starting_xi", pa.bool_()),
    ("has_batted", pa.bool_()),
    ("has_bowled", pa.bool_()),
    ("has_fielded", pa.bool_()),
    ("batting_position", pa.int8()),
    ("runs_scored", pa.int16()),
    ("balls_faced", pa.int16()),
    ("boundary_fours", pa.int8()),
    ("boundary_sixes", pa.int8()),
    ("dot_balls_faced", pa.int16()),
    ("is_dismissed", pa.bool_()),
    ("dismissals_count", pa.int8()),
    ("dismissal_kind", pa.string()),
    ("strike_rate", pa.float32()),
    ("boundary_pct", pa.float32()),
    ("dot_pct_faced", pa.float32()),
    ("legal_balls_bowled", pa.int16()),
    ("overs_bowled", pa.float32()),
    ("runs_conceded", pa.int16()),
    ("wickets_credited", pa.int8()),
    ("dot_balls_bowled", pa.int16()),
    ("boundaries_conceded", pa.int16()),
    ("maiden_overs", pa.int8()),
    ("economy_rate", pa.float32()),
    ("bowling_strike_rate", pa.float32()),
    ("bowling_average", pa.float32()),
    ("catches_taken", pa.int8()),
    ("stumpings_taken", pa.int8()),
    ("runouts_involved", pa.int8()),
    ("total_fielding_involvements", pa.int8()),
    ("batting_load", pa.float32()),
    ("bowling_load", pa.float32()),
    ("allrounder_balance_index", pa.float32()),
])

ROLLING_MATCH_SCHEMA = pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("window_size", pa.int8()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("matches_in_window", pa.int8()),
    ("rolling_runs_scored", pa.int32()),
    ("rolling_balls_faced", pa.int32()),
    ("rolling_dismissals_count", pa.int16()),
    ("rolling_batting_sr", pa.float32()),
    ("rolling_batting_avg", pa.float32()),
    ("rolling_boundary_pct", pa.float32()),
    ("rolling_dot_pct_faced", pa.float32()),
    ("rolling_legal_balls_bowled", pa.int32()),
    ("rolling_overs_bowled", pa.float32()),
    ("rolling_runs_conceded", pa.int32()),
    ("rolling_wickets_taken", pa.int16()),
    ("rolling_economy_rate", pa.float32()),
    ("rolling_bowling_sr", pa.float32()),
    ("rolling_bowling_avg", pa.float32()),
    ("rolling_dot_pct_bowled", pa.float32()),
    ("rolling_maidens_count", pa.int16()),
    ("rolling_catches", pa.int16()),
    ("rolling_stumpings", pa.int16()),
    ("rolling_runouts", pa.int16()),
    ("decayed_batting_sr", pa.float32()),
    ("decayed_economy_rate", pa.float32()),
    ("shrunk_batting_sr", pa.float32()),
    ("shrunk_economy_rate", pa.float32()),
    ("mean_batting_load", pa.float32()),
    ("mean_bowling_load", pa.float32()),
    ("mean_allrounder_index", pa.float32()),
    ("days_since_last_match", pa.int16()),
])

ROLLING_TIME_SCHEMA = pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("window_days", pa.int16()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("matches_in_window", pa.int8()),
    ("rolling_runs_scored", pa.int32()),
    ("rolling_balls_faced", pa.int32()),
    ("rolling_dismissals_count", pa.int16()),
    ("rolling_batting_sr", pa.float32()),
    ("rolling_batting_avg", pa.float32()),
    ("rolling_legal_balls_bowled", pa.int32()),
    ("rolling_runs_conceded", pa.int32()),
    ("rolling_wickets_taken", pa.int16()),
    ("rolling_economy_rate", pa.float32()),
    ("decayed_batting_sr", pa.float32()),
    ("decayed_economy_rate", pa.float32()),
    ("days_since_last_match", pa.int16()),
])

CONTEXTUAL_FEATURES_SCHEMA = pa.schema([
    ("player_id", pa.string()),
    ("match_id", pa.string()),
    ("match_format", pa.string()),
    ("season", pa.string()),
    ("evaluation_date", pa.date32()),
    ("venue_name", pa.string()),
    ("canonical_venue_name", pa.string()),
    ("opposition_team", pa.string()),
    ("venue_historical_park_factor", pa.float32()),
    ("opposition_bowling_quality_index", pa.float32()),
    ("opposition_batting_quality_index", pa.float32()),
    ("is_home_match", pa.bool_()),
    ("is_neutral_match", pa.bool_()),
    ("competition_tier_multiplier", pa.float32()),
    ("career_powerplay_strike_rate", pa.float32()),
    ("career_death_strike_rate", pa.float32()),
    ("career_powerplay_economy", pa.float32()),
    ("career_death_economy", pa.float32()),
])
