"""
CricEngine AI — Step 4B: Rolling Window Features Generator

Implements point-in-time temporal aggregations:
- Match-based rolling windows (L5, L10, L20).
- Time-based rolling windows (30d, 90d, 365d).
- Exponential recency decay with format-specific half-lives.
- Empirical Bayes cohort shrinkage for low-sample windows.
- Strict preceding-only window frames (zero future leakage).
"""
from __future__ import annotations

import math
import duckdb
import numpy as np
import pandas as pd
from typing import Dict, List, Optional

from etl.feature_definitions import (
    COHORT_PRIORS,
    FORMAT_HALF_LIVES_DAYS,
    MATCH_WINDOWS,
    MIN_SAMPLE_REQUIREMENTS,
    ROLLING_MATCH_SCHEMA,
    ROLLING_TIME_SCHEMA,
    SHRINKAGE_STRENGTH_BATTING_BALLS,
    SHRINKAGE_STRENGTH_BOWLING_BALLS,
    TIME_WINDOWS_DAYS,
)


def generate_rolling_match_features_df(
    con: duckdb.DuckDBPyConnection,
    player_match_table_or_view: str,
    window_size: int,
) -> pd.DataFrame:
    """
    Generate match-based rolling window features (e.g. L5, L10, L20)
    using strictly preceding rows (ROWS BETWEEN window_size PRECEDING AND 1 PRECEDING).
    """
    table_cols = [c[0] for c in con.execute(f"SELECT column_name FROM (DESCRIBE {player_match_table_or_view})").fetchall()]
    dismissal_col_expr = "COALESCE(dismissals_count, 0) AS dismissals_count" if "dismissals_count" in table_cols else "CASE WHEN is_dismissed = TRUE THEN 1 ELSE 0 END AS dismissals_count"

    query = f"""
    WITH ranked_pm AS (
        SELECT 
            player_id,
            match_id,
            match_format,
            season,
            start_date,
            COALESCE(batting_position, 11) AS batting_position,
            runs_scored,
            balls_faced,
            boundary_fours,
            boundary_sixes,
            dot_balls_faced,
            {dismissal_col_expr},
            legal_balls_bowled,
            runs_conceded,
            wickets_credited,
            dot_balls_bowled,
            maiden_overs,
            catches_taken,
            stumpings_taken,
            runouts_involved,
            batting_load,
            bowling_load,
            allrounder_balance_index,
            COALESCE(match_type_number, 0) AS mtn
        FROM {player_match_table_or_view}
    ),
    rolling_aggregates AS (
        SELECT 
            player_id,
            match_id,
            {window_size} AS window_size,
            match_format,
            season,
            start_date AS evaluation_date,
            COUNT(*) OVER w AS matches_in_window,
            SUM(COALESCE(runs_scored, 0)) OVER w AS rolling_runs_scored,
            SUM(COALESCE(balls_faced, 0)) OVER w AS rolling_balls_faced,
            SUM(dismissals_count) OVER w AS rolling_dismissals_count,
            SUM(COALESCE(boundary_fours, 0) + COALESCE(boundary_sixes, 0)) OVER w AS rolling_boundaries,
            SUM(COALESCE(dot_balls_faced, 0)) OVER w AS rolling_dots_faced,
            SUM(COALESCE(legal_balls_bowled, 0)) OVER w AS rolling_legal_balls_bowled,
            ROUND(SUM(COALESCE(legal_balls_bowled, 0)) OVER w / 6.0, 1) AS rolling_overs_bowled,
            SUM(COALESCE(runs_conceded, 0)) OVER w AS rolling_runs_conceded,
            SUM(COALESCE(wickets_credited, 0)) OVER w AS rolling_wickets_taken,
            SUM(COALESCE(dot_balls_bowled, 0)) OVER w AS rolling_dots_bowled,
            SUM(COALESCE(maiden_overs, 0)) OVER w AS rolling_maidens_count,
            SUM(COALESCE(catches_taken, 0)) OVER w AS rolling_catches,
            SUM(COALESCE(stumpings_taken, 0)) OVER w AS rolling_stumpings,
            SUM(COALESCE(runouts_involved, 0)) OVER w AS rolling_runouts,
            ROUND(AVG(COALESCE(batting_load, 0.0)) OVER w, 4) AS mean_batting_load,
            ROUND(AVG(COALESCE(bowling_load, 0.0)) OVER w, 4) AS mean_bowling_load,
            ROUND(AVG(COALESCE(allrounder_balance_index, 0.0)) OVER w, 4) AS mean_allrounder_index,
            DATE_DIFF('day', LAG(start_date) OVER (
                PARTITION BY player_id, match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
            ), start_date) AS days_since_last_match
        FROM ranked_pm
        WINDOW w AS (
            PARTITION BY player_id, match_format
            ORDER BY start_date ASC, mtn ASC, match_id ASC
            ROWS BETWEEN {window_size} PRECEDING AND 1 PRECEDING
        )
    )
    SELECT 
        player_id,
        match_id,
        window_size,
        match_format,
        season,
        evaluation_date,
        matches_in_window,
        rolling_runs_scored,
        rolling_balls_faced,
        rolling_dismissals_count,
        -- Strike Rate (Min balls: T20=30, ODI=60, Test=100)
        CASE 
            WHEN match_format = 'T20' AND rolling_balls_faced >= 30 THEN ROUND((rolling_runs_scored * 100.0) / rolling_balls_faced, 2)
            WHEN match_format = 'ODI' AND rolling_balls_faced >= 60 THEN ROUND((rolling_runs_scored * 100.0) / rolling_balls_faced, 2)
            WHEN match_format = 'Test' AND rolling_balls_faced >= 100 THEN ROUND((rolling_runs_scored * 100.0) / rolling_balls_faced, 2)
            ELSE NULL 
        END AS rolling_batting_sr,
        -- Batting Average (Min dismissals: T20=5, ODI=8, Test=10)
        CASE 
            WHEN match_format = 'T20' AND rolling_dismissals_count >= 5 THEN ROUND((rolling_runs_scored * 1.0) / rolling_dismissals_count, 2)
            WHEN match_format = 'ODI' AND rolling_dismissals_count >= 8 THEN ROUND((rolling_runs_scored * 1.0) / rolling_dismissals_count, 2)
            WHEN match_format = 'Test' AND rolling_dismissals_count >= 10 THEN ROUND((rolling_runs_scored * 1.0) / rolling_dismissals_count, 2)
            ELSE NULL 
        END AS rolling_batting_avg,
        -- Boundary %
        CASE 
            WHEN rolling_balls_faced >= 20 THEN ROUND((rolling_boundaries * 100.0) / rolling_balls_faced, 2)
            ELSE NULL 
        END AS rolling_boundary_pct,
        -- Dot % Faced
        CASE 
            WHEN rolling_balls_faced >= 20 THEN ROUND((rolling_dots_faced * 100.0) / rolling_balls_faced, 2)
            ELSE NULL 
        END AS rolling_dot_pct_faced,
        rolling_legal_balls_bowled,
        rolling_overs_bowled,
        rolling_runs_conceded,
        rolling_wickets_taken,
        -- Economy Rate (Min legal balls: T20=60, ODI=120, Test=180)
        CASE 
            WHEN match_format = 'T20' AND rolling_legal_balls_bowled >= 60 THEN ROUND((rolling_runs_conceded * 6.0) / rolling_legal_balls_bowled, 2)
            WHEN match_format = 'ODI' AND rolling_legal_balls_bowled >= 120 THEN ROUND((rolling_runs_conceded * 6.0) / rolling_legal_balls_bowled, 2)
            WHEN match_format = 'Test' AND rolling_legal_balls_bowled >= 180 THEN ROUND((rolling_runs_conceded * 6.0) / rolling_legal_balls_bowled, 2)
            ELSE NULL 
        END AS rolling_economy_rate,
        -- Bowling Strike Rate (Min 5 wickets and legal balls)
        CASE 
            WHEN rolling_wickets_taken >= 5 AND rolling_legal_balls_bowled >= 60 THEN ROUND((rolling_legal_balls_bowled * 1.0) / rolling_wickets_taken, 2)
            ELSE NULL 
        END AS rolling_bowling_sr,
        -- Bowling Average
        CASE 
            WHEN rolling_wickets_taken >= 5 AND rolling_legal_balls_bowled >= 60 THEN ROUND((rolling_runs_conceded * 1.0) / rolling_wickets_taken, 2)
            ELSE NULL 
        END AS rolling_bowling_avg,
        -- Dot % Bowled
        CASE 
            WHEN rolling_legal_balls_bowled >= 30 THEN ROUND((rolling_dots_bowled * 100.0) / rolling_legal_balls_bowled, 2)
            ELSE NULL 
        END AS rolling_dot_pct_bowled,
        rolling_maidens_count,
        rolling_catches,
        rolling_stumpings,
        rolling_runouts,
        -- Bayesian Shrunk Batting Strike Rate (M = 40)
        CASE 
            WHEN rolling_balls_faced > 0 THEN 
                ROUND(
                    ((rolling_balls_faced * 1.0 / (rolling_balls_faced + 40.0)) * (rolling_runs_scored * 100.0 / rolling_balls_faced)) +
                    ((40.0 / (rolling_balls_faced + 40.0)) * 
                        CASE match_format WHEN 'T20' THEN 130.0 WHEN 'ODI' THEN 85.0 ELSE 52.0 END
                    ), 2
                )
            ELSE NULL 
        END AS shrunk_batting_sr,
        -- Bayesian Shrunk Economy Rate (M = 30)
        CASE 
            WHEN rolling_legal_balls_bowled > 0 THEN 
                ROUND(
                    ((rolling_legal_balls_bowled * 1.0 / (rolling_legal_balls_bowled + 30.0)) * (rolling_runs_conceded * 6.0 / rolling_legal_balls_bowled)) +
                    ((30.0 / (rolling_legal_balls_bowled + 30.0)) * 
                        CASE match_format WHEN 'T20' THEN 8.10 WHEN 'ODI' THEN 5.25 ELSE 3.15 END
                    ), 2
                )
            ELSE NULL 
        END AS shrunk_economy_rate,
        mean_batting_load,
        mean_bowling_load,
        mean_allrounder_index,
        days_since_last_match
    FROM rolling_aggregates
    """
    df = con.execute(query).df()

    # Calculate exponential recency decay metrics in Python
    decayed_srs = []
    decayed_econs = []
    for _, row in df.iterrows():
        fmt = str(row["match_format"])
        half_life = FORMAT_HALF_LIVES_DAYS.get(fmt, 90.0)
        priors = COHORT_PRIORS.get(fmt, COHORT_PRIORS["T20"])
        days_gap = row["days_since_last_match"]

        if pd.isna(days_gap) or days_gap is None:
            decay_factor = 1.0
        else:
            decay_factor = math.pow(2.0, -min(365.0, float(days_gap)) / half_life)

        raw_sr = row["rolling_batting_sr"]
        if pd.isna(raw_sr) or raw_sr is None:
            decayed_srs.append(None)
        else:
            decayed_val = (float(raw_sr) * decay_factor) + (priors["batting_strike_rate"] * (1.0 - decay_factor))
            decayed_srs.append(round(decayed_val, 2))

        raw_econ = row["rolling_economy_rate"]
        if pd.isna(raw_econ) or raw_econ is None:
            decayed_econs.append(None)
        else:
            decayed_econ_val = (float(raw_econ) * decay_factor) + (priors["bowling_economy_rate"] * (1.0 - decay_factor))
            decayed_econs.append(round(decayed_econ_val, 2))

    df["decayed_batting_sr"] = decayed_srs
    df["decayed_economy_rate"] = decayed_econs

    ordered_cols = [
        "player_id", "match_id", "window_size", "match_format", "season", "evaluation_date",
        "matches_in_window", "rolling_runs_scored", "rolling_balls_faced", "rolling_dismissals_count",
        "rolling_batting_sr", "rolling_batting_avg", "rolling_boundary_pct", "rolling_dot_pct_faced",
        "rolling_legal_balls_bowled", "rolling_overs_bowled", "rolling_runs_conceded", "rolling_wickets_taken",
        "rolling_economy_rate", "rolling_bowling_sr", "rolling_bowling_avg", "rolling_dot_pct_bowled",
        "rolling_maidens_count", "rolling_catches", "rolling_stumpings", "rolling_runouts",
        "decayed_batting_sr", "decayed_economy_rate", "shrunk_batting_sr", "shrunk_economy_rate",
        "mean_batting_load", "mean_bowling_load", "mean_allrounder_index", "days_since_last_match"
    ]
    return df[ordered_cols]


def generate_rolling_time_features_df(
    con: duckdb.DuckDBPyConnection,
    player_match_table_or_view: str,
    window_days: int,
) -> pd.DataFrame:
    """
    Generate time-based rolling window features (e.g. 30d, 90d, 365d)
    using RANGE BETWEEN INTERVAL window_days DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING.
    Strictly excludes current match date.
    """
    table_cols = [c[0] for c in con.execute(f"SELECT column_name FROM (DESCRIBE {player_match_table_or_view})").fetchall()]
    dismissal_col_expr = "COALESCE(dismissals_count, 0) AS dismissals_count" if "dismissals_count" in table_cols else "CASE WHEN is_dismissed = TRUE THEN 1 ELSE 0 END AS dismissals_count"

    query = f"""
    WITH ranked_pm AS (
        SELECT 
            player_id,
            match_id,
            match_format,
            season,
            start_date,
            runs_scored,
            balls_faced,
            {dismissal_col_expr},
            legal_balls_bowled,
            runs_conceded,
            wickets_credited,
            COALESCE(match_type_number, 0) AS mtn
        FROM {player_match_table_or_view}
    ),
    time_aggregates AS (
        SELECT 
            player_id,
            match_id,
            {window_days} AS window_days,
            match_format,
            season,
            start_date AS evaluation_date,
            COUNT(*) OVER w AS matches_in_window,
            SUM(COALESCE(runs_scored, 0)) OVER w AS rolling_runs_scored,
            SUM(COALESCE(balls_faced, 0)) OVER w AS rolling_balls_faced,
            SUM(dismissals_count) OVER w AS rolling_dismissals_count,
            SUM(COALESCE(legal_balls_bowled, 0)) OVER w AS rolling_legal_balls_bowled,
            SUM(COALESCE(runs_conceded, 0)) OVER w AS rolling_runs_conceded,
            SUM(COALESCE(wickets_credited, 0)) OVER w AS rolling_wickets_taken,
            DATE_DIFF('day', LAG(start_date) OVER (
                PARTITION BY player_id, match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
            ), start_date) AS days_since_last_match
        FROM ranked_pm
        WINDOW w AS (
            PARTITION BY player_id, match_format
            ORDER BY start_date
            RANGE BETWEEN INTERVAL {window_days} DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING
        )
    )
    SELECT 
        player_id,
        match_id,
        window_days,
        match_format,
        season,
        evaluation_date,
        matches_in_window,
        rolling_runs_scored,
        rolling_balls_faced,
        rolling_dismissals_count,
        CASE 
            WHEN rolling_balls_faced >= 25 THEN ROUND((rolling_runs_scored * 100.0) / rolling_balls_faced, 2)
            ELSE NULL 
        END AS rolling_batting_sr,
        CASE 
            WHEN rolling_dismissals_count >= 3 THEN ROUND((rolling_runs_scored * 1.0) / rolling_dismissals_count, 2)
            ELSE NULL 
        END AS rolling_batting_avg,
        rolling_legal_balls_bowled,
        rolling_runs_conceded,
        rolling_wickets_taken,
        CASE 
            WHEN rolling_legal_balls_bowled >= 36 THEN ROUND((rolling_runs_conceded * 6.0) / rolling_legal_balls_bowled, 2)
            ELSE NULL 
        END AS rolling_economy_rate,
        days_since_last_match
    FROM time_aggregates
    """
    df = con.execute(query).df()

    decayed_srs = []
    decayed_econs = []
    for _, row in df.iterrows():
        fmt = str(row["match_format"])
        half_life = FORMAT_HALF_LIVES_DAYS.get(fmt, 90.0)
        priors = COHORT_PRIORS.get(fmt, COHORT_PRIORS["T20"])
        days_gap = row["days_since_last_match"]

        if pd.isna(days_gap) or days_gap is None:
            decay_factor = 1.0
        else:
            decay_factor = math.pow(2.0, -min(365.0, float(days_gap)) / half_life)

        raw_sr = row["rolling_batting_sr"]
        if pd.isna(raw_sr) or raw_sr is None:
            decayed_srs.append(None)
        else:
            decayed_val = (float(raw_sr) * decay_factor) + (priors["batting_strike_rate"] * (1.0 - decay_factor))
            decayed_srs.append(round(decayed_val, 2))

        raw_econ = row["rolling_economy_rate"]
        if pd.isna(raw_econ) or raw_econ is None:
            decayed_econs.append(None)
        else:
            decayed_econ_val = (float(raw_econ) * decay_factor) + (priors["bowling_economy_rate"] * (1.0 - decay_factor))
            decayed_econs.append(round(decayed_econ_val, 2))

    df["decayed_batting_sr"] = decayed_srs
    df["decayed_economy_rate"] = decayed_econs

    ordered_cols = [
        "player_id", "match_id", "window_days", "match_format", "season", "evaluation_date",
        "matches_in_window", "rolling_runs_scored", "rolling_balls_faced", "rolling_dismissals_count",
        "rolling_batting_sr", "rolling_batting_avg", "rolling_legal_balls_bowled", "rolling_runs_conceded",
        "rolling_wickets_taken", "rolling_economy_rate", "decayed_batting_sr", "decayed_economy_rate",
        "days_since_last_match"
    ]
    return df[ordered_cols]
