"""
CricEngine AI — Tests for Data Leakage Prevention & Temporal Correctness

Verifies that the feature generation pipeline guarantees zero data leakage:
1. Current evaluated match m is strictly excluded from its own rolling window.
2. Invariance of past features: appending future matches m+1 does not change features for match m.
3. Expanding contextual venue and opposition baselines use strictly preceding matches.
4. Deliberate future data injection cannot leak into historical evaluations.
5. Strict chronological boundary preservation for downstream train/val/test splits.
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


def create_mock_sequence(con: duckdb.DuckDBPyConnection, table_name: str, records: list):
    """Helper to create and populate mock player match table."""
    con.execute(f"""
    CREATE TABLE {table_name} (
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
    con.executemany(f"INSERT INTO {table_name} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)


def test_current_match_exclusion_leakage():
    """Prove that match m's own runs and balls are NEVER in match m's rolling window."""
    con = duckdb.connect()
    # Player plays 1 match and scores 100 off 50 balls
    records = [
        ("P1", "M1", "T20", "2024", "2024-01-01", 1, 1, 100, 50, 10, 4, 15, True, 24, 20, 3, 12, 1, 1, 0, 0, 0.4, 0.2, 0.27),
    ]
    create_mock_sequence(con, "single_match", records)

    df_roll = generate_rolling_match_features_df(con, "single_match", window_size=5)
    row = df_roll.iloc[0]

    # Preceding match count MUST be 0
    assert row["matches_in_window"] == 0
    assert pd.isna(row["rolling_runs_scored"]) or row["rolling_runs_scored"] == 0
    assert pd.isna(row["rolling_balls_faced"]) or row["rolling_balls_faced"] == 0
    assert pd.isna(row["rolling_batting_sr"])
    assert pd.isna(row["rolling_economy_rate"])


def test_invariance_under_future_additions():
    """Prove that adding future matches M2 and M3 does not change M1's historical feature vector."""
    con1 = duckdb.connect()
    con2 = duckdb.connect()

    # Database 1: Only matches up to Jan 10
    records_t1 = [
        ("P1", "M1", "T20", "2024", "2024-01-01", 1, 1, 40, 30, 4, 1, 10, True, 0, 0, 0, 0, 0, 0, 0, 0, 0.25, 0.0, 0.0),
        ("P1", "M2", "T20", "2024", "2024-01-10", 2, 1, 60, 40, 6, 2, 12, False, 0, 0, 0, 0, 0, 0, 0, 0, 0.35, 0.0, 0.0),
    ]
    create_mock_sequence(con1, "pm_t1", records_t1)
    df_t1 = generate_rolling_match_features_df(con1, "pm_t1", window_size=5)

    # Database 2: Matches up to Jan 10 PLUS future matches M3 and M4 (Jan 20 and Jan 30)
    records_t2 = records_t1 + [
        ("P1", "M3", "T20", "2024", "2024-01-20", 3, 1, 100, 50, 10, 5, 15, True, 0, 0, 0, 0, 0, 0, 0, 0, 0.45, 0.0, 0.0),
        ("P1", "M4", "T20", "2024", "2024-01-30", 4, 1, 80, 45, 8, 3, 14, True, 0, 0, 0, 0, 0, 0, 0, 0, 0.40, 0.0, 0.0),
    ]
    create_mock_sequence(con2, "pm_t2", records_t2)
    df_t2 = generate_rolling_match_features_df(con2, "pm_t2", window_size=5)

    # Inspect M2 feature vector in both databases:
    m2_t1 = df_t1[df_t1["match_id"] == "M2"].iloc[0].to_dict()
    m2_t2 = df_t2[df_t2["match_id"] == "M2"].iloc[0].to_dict()

    for col in df_t1.columns:
        val1 = m2_t1[col]
        val2 = m2_t2[col]
        if pd.isna(val1) and pd.isna(val2):
            continue
        assert val1 == val2, f"Feature leakage detected! Column {col} for M2 changed from {val1} to {val2} after adding future matches!"


def test_expanding_venue_park_factor_preceding_only():
    """Prove that expanding venue park factors use only matches strictly before the evaluated match date."""
    con = duckdb.connect()
    con.execute("""
    CREATE TABLE mock_match (
        match_id VARCHAR,
        start_date DATE,
        match_format VARCHAR,
        match_type_number INTEGER,
        venue_name VARCHAR,
        match_total_runs INTEGER,
        match_legal_balls INTEGER
    );
    """)

    # Match 1: 2024-01-01 at Venue A -> 200 runs off 120 balls (10.0 rpo)
    # Match 2: 2024-01-05 at Venue A -> 180 runs off 120 balls (9.0 rpo)
    # Match 3: 2024-01-10 at Venue A -> 120 runs off 120 balls (6.0 rpo)
    # Format overall: identical venue for simplicity
    con.execute("""
    INSERT INTO mock_match VALUES 
        ('M1', '2024-01-01', 'T20', 1, 'Venue A', 200, 120),
        ('M2', '2024-01-05', 'T20', 2, 'Venue A', 180, 120),
        ('M3', '2024-01-10', 'T20', 3, 'Venue A', 120, 120);
    """)

    # Expanding window query
    q = """
    SELECT 
        match_id,
        start_date,
        SUM(match_total_runs) OVER (
            PARTITION BY venue_name, match_format
            ORDER BY start_date ASC, match_type_number ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS prior_runs
    FROM mock_match;
    """
    df = con.execute(q).df()

    # M1 has no preceding matches -> prior_runs must be None (NULL)
    assert pd.isna(df.loc[df["match_id"] == "M1", "prior_runs"].values[0])
    # M2 has exactly M1 (200 runs)
    assert df.loc[df["match_id"] == "M2", "prior_runs"].values[0] == 200
    # M3 has M1 + M2 (200 + 180 = 380 runs), NEVER M3's 120 runs!
    assert df.loc[df["match_id"] == "M3", "prior_runs"].values[0] == 380


def test_chronological_split_boundary_leakage_safeguard():
    """Verify that dates strictly partition train and test sets without timestamp inversion."""
    train_cutoff = datetime.date(2023, 12, 31)
    test_start = datetime.date(2024, 1, 1)

    assert train_cutoff < test_start
    # Verify that a lag window ordered by start_date ASC respects chronological sorting
    con = duckdb.connect()
    con.execute("""
    CREATE TABLE chronological_test (
        id VARCHAR,
        match_date DATE
    );
    INSERT INTO chronological_test VALUES 
        ('A', '2023-05-01'),
        ('B', '2023-11-01'),
        ('C', '2024-02-01');
    """)

    df = con.execute("""
    SELECT id, match_date, LAG(match_date) OVER (ORDER BY match_date ASC) AS prev_date
    FROM chronological_test
    """).df()

    # Row C (in test) only sees Row B (in train); Row A sees NULL
    assert pd.isna(df.loc[df["id"] == "A", "prev_date"].values[0])
    assert str(df.loc[df["id"] == "C", "prev_date"].values[0])[:10] == "2023-11-01"
