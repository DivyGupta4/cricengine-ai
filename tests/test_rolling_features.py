"""
CricEngine AI — Tests for Rolling Features, Sample Thresholds & Bayesian Shrinkage
"""
from __future__ import annotations

import datetime
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import pytest

from etl.rolling_features import (
    generate_rolling_match_features_df,
    generate_rolling_time_features_df,
)
from etl.feature_definitions import (
    COHORT_PRIORS,
    FORMAT_HALF_LIVES_DAYS,
    MIN_SAMPLE_REQUIREMENTS,
)


@pytest.fixture
def memory_db_with_mock_player_matches():
    """Create in-memory DuckDB connection with controlled synthetic player-match sequences."""
    con = duckdb.connect()
    con.execute("""
    CREATE TABLE mock_player_match (
        player_id VARCHAR,
        match_id VARCHAR,
        match_format VARCHAR,
        season VARCHAR,
        start_date DATE,
        match_type_number INTEGER,
        batting_position INTEGER,
        runs_scored INTEGER,
        balls_faced INTEGER,
        boundary_fours INTEGER,
        boundary_sixes INTEGER,
        dot_balls_faced INTEGER,
        is_dismissed BOOLEAN,
        legal_balls_bowled INTEGER,
        runs_conceded INTEGER,
        wickets_credited INTEGER,
        dot_balls_bowled INTEGER,
        maiden_overs INTEGER,
        catches_taken INTEGER,
        stumpings_taken INTEGER,
        runouts_involved INTEGER,
        batting_load FLOAT,
        bowling_load FLOAT,
        allrounder_balance_index FLOAT
    );
    """)

    # Insert a sequence of 6 T20 matches for player 'P1'
    # Match 1: 2024-01-01 -> 15 runs, 10 balls (dismissed)
    # Match 2: 2024-01-10 -> 25 runs, 15 balls (not out)
    # Match 3: 2024-01-20 -> 40 runs, 20 balls (dismissed)
    # Match 4: 2024-01-30 -> 10 runs, 5 balls (dismissed)
    # Match 5: 2024-02-10 -> 50 runs, 30 balls (not out)
    # Match 6: 2024-02-20 -> 30 runs, 20 balls (dismissed)
    records = [
        ("P1", "M1", "T20", "2024", "2024-01-01", 1, 3, 15, 10, 2, 0, 3, True, 0, 0, 0, 0, 0, 0, 0, 0, 0.1, 0.0, 0.0),
        ("P1", "M2", "T20", "2024", "2024-01-10", 2, 3, 25, 15, 3, 1, 4, False, 12, 16, 1, 5, 0, 1, 0, 0, 0.15, 0.1, 0.12),
        ("P1", "M3", "T20", "2024", "2024-01-20", 3, 3, 40, 20, 4, 2, 5, True, 24, 28, 2, 10, 0, 0, 0, 0, 0.2, 0.2, 0.2),
        ("P1", "M4", "T20", "2024", "2024-01-30", 4, 3, 10, 5, 1, 0, 2, True, 24, 32, 0, 8, 0, 0, 0, 0, 0.05, 0.2, 0.08),
        ("P1", "M5", "T20", "2024", "2024-02-10", 5, 3, 50, 30, 5, 2, 8, False, 0, 0, 0, 0, 0, 2, 0, 0, 0.3, 0.0, 0.0),
        ("P1", "M6", "T20", "2024", "2024-02-20", 6, 3, 30, 20, 3, 1, 5, True, 24, 20, 3, 12, 1, 0, 0, 0, 0.2, 0.2, 0.2),
    ]
    con.executemany("INSERT INTO mock_player_match VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)
    return con


def test_rolling_match_window_preceding_only(memory_db_with_mock_player_matches):
    """Verify that match window strictly aggregates preceding matches (never including current)."""
    con = memory_db_with_mock_player_matches
    df_roll = generate_rolling_match_features_df(con, "mock_player_match", window_size=5)

    # For Match 1: No preceding matches -> matches_in_window must be 0
    m1 = df_roll[df_roll["match_id"] == "M1"].iloc[0]
    assert m1["matches_in_window"] == 0
    assert pd.isna(m1["rolling_runs_scored"]) or m1["rolling_runs_scored"] == 0
    assert pd.isna(m1["rolling_balls_faced"]) or m1["rolling_balls_faced"] == 0
    assert pd.isna(m1["rolling_batting_sr"])

    # For Match 2: Exactly Match 1 precedes (15 runs, 10 balls)
    m2 = df_roll[df_roll["match_id"] == "M2"].iloc[0]
    assert m2["matches_in_window"] == 1
    assert m2["rolling_runs_scored"] == 15
    assert m2["rolling_balls_faced"] == 10
    # 10 balls < min sample requirement (30) -> rolling_batting_sr must be NULL
    assert pd.isna(m2["rolling_batting_sr"])

    # For Match 4: Matches M1, M2, M3 precede:
    # Runs = 15 + 25 + 40 = 80
    # Balls = 10 + 15 + 20 = 45 (>= 30 balls threshold)
    m4 = df_roll[df_roll["match_id"] == "M4"].iloc[0]
    assert m4["matches_in_window"] == 3
    assert m4["rolling_runs_scored"] == 80
    assert m4["rolling_balls_faced"] == 45
    expected_sr = round((80 * 100.0) / 45, 2)
    assert m4["rolling_batting_sr"] == expected_sr

    # For Match 6 with window 5: Matches M1..M5 precede (exactly 5 matches)
    # Runs = 15 + 25 + 40 + 10 + 50 = 140
    # Balls = 10 + 15 + 20 + 5 + 30 = 80
    m6 = df_roll[df_roll["match_id"] == "M6"].iloc[0]
    assert m6["matches_in_window"] == 5
    assert m6["rolling_runs_scored"] == 140
    assert m6["rolling_balls_faced"] == 80
    assert m6["rolling_batting_sr"] == round((140 * 100.0) / 80, 2)


def test_rolling_time_window_date_exclusion(memory_db_with_mock_player_matches):
    """Verify that rolling time window excludes the evaluated fixture date."""
    con = memory_db_with_mock_player_matches
    df_time = generate_rolling_time_features_df(con, "mock_player_match", window_days=30)

    # For M1 (2024-01-01): 0 matches in preceding 30 days
    m1 = df_time[df_time["match_id"] == "M1"].iloc[0]
    assert m1["matches_in_window"] == 0

    # For M4 (2024-01-30): Preceding 30 days are [2024-01-01 to 2024-01-29] -> includes M1 (Jan 1), M2 (Jan 10), M3 (Jan 20)
    m4 = df_time[df_time["match_id"] == "M4"].iloc[0]
    assert m4["matches_in_window"] == 3
    assert m4["rolling_runs_scored"] == 80

    # For M6 (2024-02-20): Preceding 30 days are [2024-01-22 to 2024-02-19] -> includes M4 (Jan 30) and M5 (Feb 10)
    # M1, M2, M3 are older than 30 days and must be excluded!
    m6 = df_time[df_time["match_id"] == "M6"].iloc[0]
    assert m6["matches_in_window"] == 2
    # Runs from M4 (10) + M5 (50) = 60
    assert m6["rolling_runs_scored"] == 60


def test_zero_conflation_policy_on_unobserved_metrics(memory_db_with_mock_player_matches):
    """Verify that unobserved performance emits NULL and is never conflated with zero."""
    con = memory_db_with_mock_player_matches
    df_roll = generate_rolling_match_features_df(con, "mock_player_match", window_size=5)

    # Match 1 had 0 preceding matches:
    m1 = df_roll[df_roll["match_id"] == "M1"].iloc[0]
    assert pd.isna(m1["rolling_batting_sr"])
    assert pd.isna(m1["rolling_batting_avg"])
    assert pd.isna(m1["rolling_economy_rate"])
    assert pd.isna(m1["shrunk_batting_sr"])
    assert pd.isna(m1["shrunk_economy_rate"])


def test_multi_innings_dismissals_in_rolling_average():
    """Verify that multi-innings Test matches with 2 dismissals accurately sum in rolling batting average."""
    con = duckdb.connect()
    con.execute("""
    CREATE TABLE mock_test_pm (
        player_id VARCHAR,
        match_id VARCHAR,
        match_format VARCHAR,
        season VARCHAR,
        start_date DATE,
        match_type_number INTEGER,
        batting_position INTEGER,
        runs_scored INTEGER,
        balls_faced INTEGER,
        boundary_fours INTEGER,
        boundary_sixes INTEGER,
        dot_balls_faced INTEGER,
        is_dismissed BOOLEAN,
        dismissals_count INTEGER,
        legal_balls_bowled INTEGER,
        runs_conceded INTEGER,
        wickets_credited INTEGER,
        dot_balls_bowled INTEGER,
        maiden_overs INTEGER,
        catches_taken INTEGER,
        stumpings_taken INTEGER,
        runouts_involved INTEGER,
        batting_load FLOAT,
        bowling_load FLOAT,
        allrounder_balance_index FLOAT
    );
    """)

    # Player plays 6 Test matches:
    # M1..M5: 100 runs off 200 balls, 2 dismissals in each match (total 500 runs, 10 dismissals over 5 matches)
    records = [
        ("P1", f"M{i}", "Test", "2024", f"2024-0{i}-01", i, 4, 100, 200, 10, 0, 120, True, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0.2, 0.0, 0.0)
        for i in range(1, 6)
    ]
    # M6 is evaluated
    records.append(
        ("P1", "M6", "Test", "2024", "2024-06-01", 6, 4, 50, 100, 5, 0, 60, True, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0.2, 0.0, 0.0)
    )
    con.executemany("INSERT INTO mock_test_pm VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)

    df_roll = generate_rolling_match_features_df(con, "mock_test_pm", window_size=5)
    m6 = df_roll[df_roll["match_id"] == "M6"].iloc[0]

    # Preceding 5 matches had 5 * 2 = 10 dismissals
    assert m6["rolling_dismissals_count"] == 10
    # Batting average must be 500 / 10 = 50.0 (if only 1 per match had been counted, it would be 5 < 10 threshold -> NULL!)
    assert m6["rolling_batting_avg"] == 50.0

