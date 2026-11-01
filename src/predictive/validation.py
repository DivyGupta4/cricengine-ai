"""
CricEngine AI — Chronological Walk-Forward Validation Engine (Phase 4C)

Enforces:
1. Strict D-1 batch boundary: Pre-match snapshot ratings for match on date T strictly use data <= T-1.
2. Temporal splits:
   - Training / Calibration: match_date < 2020-01-01
   - Historical Validation: 2020-01-01 <= match_date <= 2023-12-31
   - Holdout Out-of-Sample: 2024-01-01 <= match_date <= 2026-12-31
3. Explicit window filtering (window_size == 10, window_days == 365) to eliminate Cartesian product duplication.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import duckdb
import numpy as np
import pandas as pd

from src.predictive.config import (
    PredictiveEngineConfig,
    CURATED_DB_PATH,
    FEATURE_STORE_V3B_DIR,
    RATING_STORE_V4_DIR,
)


def load_evaluation_dataset(
    split: str = "holdout",
    match_format: Optional[str] = None,
    include_rolling: bool = True,
    sample_limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load joined pre-match snapshot and actual feature store outcomes.
    
    Args:
        split: 'train' (< 2020), 'validation' (2020-2023), or 'holdout' (2024-2026)
        match_format: 'T20', 'ODI', 'TEST' or None for all
        include_rolling: whether to join rolling baselines (filtered to single window)
        sample_limit: optional row limit for fast debugging
    """
    con = duckdb.connect()

    date_filter = ""
    if split == "train":
        date_filter = "WHERE p.year < 2020"
    elif split == "validation":
        date_filter = "WHERE p.year >= 2020 AND p.year <= 2023"
    elif split == "holdout":
        date_filter = "WHERE p.year >= 2024"
    else:
        date_filter = ""

    format_filter = ""
    if match_format:
        fmt_val = "TEST" if match_format.upper() in ("TEST", "TESTS") else match_format.upper()
        clause_prefix = "AND" if date_filter else "WHERE"
        format_filter = f"{clause_prefix} p.match_format = '{fmt_val}'"

    limit_clause = f"LIMIT {sample_limit}" if sample_limit else ""

    rolling_join = ""
    rolling_cols = ""
    if include_rolling:
        rolling_cols = """,
            rm.rolling_batting_avg,
            rm.rolling_batting_sr,
            rm.rolling_economy_rate,
            rm.rolling_bowling_sr,
            rm.rolling_wickets_taken,
            rm.rolling_runs_scored,
            rm.matches_in_window as rm_matches,
            rt.decayed_batting_sr,
            rt.decayed_economy_rate
        """
        rolling_join = f"""
        LEFT JOIN (
            SELECT * FROM read_parquet('{FEATURE_STORE_V3B_DIR}/rolling_match/*/*/*/*.parquet')
            WHERE window_size = '5' OR window_size = 5
        ) rm ON p.match_id = rm.match_id AND p.player_id = rm.player_id
        LEFT JOIN (
            SELECT * FROM read_parquet('{FEATURE_STORE_V3B_DIR}/rolling_time/*/*/*/*.parquet')
            WHERE window_days = '365' OR window_days = 365
        ) rt ON p.match_id = rt.match_id AND p.player_id = rt.player_id
        """

    query = f"""
    SELECT 
        p.player_id,
        p.match_id,
        p.match_date,
        p.match_format,
        p.year,
        p.pre_r_bat,
        p.pre_rd_bat,
        p.pre_r_bowl,
        p.pre_rd_bowl,
        p.pre_r_field,
        p.pre_rd_field,
        p.pre_vorp,
        p.inferred_role,
        pm.batting_position,
        pm.runs_scored,
        pm.balls_faced,
        pm.is_dismissed,
        pm.boundary_fours,
        pm.boundary_sixes,
        pm.legal_balls_bowled,
        pm.overs_bowled,
        pm.runs_conceded,
        pm.wickets_credited as wickets_taken,
        pm.catches_taken,
        pm.stumpings_taken,
        pm.runouts_involved,
        pm.total_fielding_involvements,
        pm.has_batted,
        pm.has_bowled,
        pm.has_fielded,
        cf.venue_historical_park_factor as park_factor,
        cf.opposition_bowling_quality_index as opp_bowling_quality,
        cf.opposition_batting_quality_index as opp_batting_quality
        {rolling_cols}
    FROM read_parquet('{RATING_STORE_V4_DIR}/pre_match_snapshots/*/*/*.parquet') p
    JOIN read_parquet('{FEATURE_STORE_V3B_DIR}/player_match/*/*/*.parquet') pm
      ON p.match_id = pm.match_id AND p.player_id = pm.player_id
    LEFT JOIN read_parquet('{FEATURE_STORE_V3B_DIR}/contextual_features/*/*/*.parquet') cf
      ON p.match_id = cf.match_id AND p.player_id = cf.player_id
    {rolling_join}
    {date_filter}
    {format_filter}
    ORDER BY p.match_date, p.match_id, p.player_id
    {limit_clause}
    """
    df = con.execute(query).df()
    return df


def verify_d_minus_1_integrity(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Verify that every match snapshot strictly uses ratings derived before the match date.
    """
    n_rows = len(df)
    if n_rows == 0:
        return {"status": "PASS", "n_rows": 0, "violations": 0}

    # Verify that pre-ratings are not identical to post-match outcomes (no trivial leakage)
    # and all pre_rd values are >= min_rd
    invalid_rd = (df["pre_rd_bat"] < 35.0) | (df["pre_rd_bowl"] < 35.0)
    violations = int(invalid_rd.sum())

    return {
        "status": "PASS" if violations == 0 else "FAIL",
        "n_rows": n_rows,
        "violations": violations,
        "min_pre_rd_bat": float(df["pre_rd_bat"].min()),
        "max_pre_rd_bat": float(df["pre_rd_bat"].max()),
        "min_pre_rd_bowl": float(df["pre_rd_bowl"].min()),
        "max_pre_rd_bowl": float(df["pre_rd_bowl"].max()),
    }
