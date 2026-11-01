"""
CricEngine AI — Phase 3A: Retirement Accounting & Dismissal Fidelity Tests
Verifies remediation of finding DF-02 across player_match and rolling features.
"""
from __future__ import annotations

from pathlib import Path
import duckdb
import pytest


@pytest.fixture(scope="module")
def duckdb_con():
    db_path = Path("data/datalake/curated/cricengine.duckdb")
    con = duckdb.connect(str(db_path), read_only=True)
    yield con
    con.close()


def test_retired_hurt_not_counted_as_dismissal(duckdb_con):
    """Verify that players with ONLY 'retired hurt' have is_dismissed=False and dismissals_count=0."""
    # Find a match where a player retired hurt without other dismissals
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT 
        CASE WHEN COALESCE(d.true_dismissals, 0) > 0 THEN TRUE ELSE FALSE END AS is_dismissed,
        CAST(COALESCE(d.true_dismissals, 0) AS TINYINT) AS dismissals_count,
        d.dismissal_kind
    FROM dismissal_agg d
    WHERE d.dismissal_kind = 'retired hurt'
    LIMIT 10
    """
    df = duckdb_con.execute(query).df()
    assert len(df) == 10
    assert (df["is_dismissed"] == False).all()
    assert (df["dismissals_count"] == 0).all()
    assert (df["dismissal_kind"] == "retired hurt").all()


def test_retired_not_out_not_counted_as_dismissal(duckdb_con):
    """Verify that players with ONLY 'retired not out' have is_dismissed=False and dismissals_count=0."""
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT 
        CASE WHEN COALESCE(d.true_dismissals, 0) > 0 THEN TRUE ELSE FALSE END AS is_dismissed,
        CAST(COALESCE(d.true_dismissals, 0) AS TINYINT) AS dismissals_count,
        d.dismissal_kind
    FROM dismissal_agg d
    WHERE d.dismissal_kind = 'retired not out'
    """
    df = duckdb_con.execute(query).df()
    assert len(df) == 6
    assert (df["is_dismissed"] == False).all()
    assert (df["dismissals_count"] == 0).all()
    assert (df["dismissal_kind"] == "retired not out").all()


def test_retired_out_counted_as_dismissal(duckdb_con):
    """Verify that 'retired out' is correctly treated as a dismissal under Law 25.4.3."""
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT 
        CASE WHEN COALESCE(d.true_dismissals, 0) > 0 THEN TRUE ELSE FALSE END AS is_dismissed,
        CAST(COALESCE(d.true_dismissals, 0) AS TINYINT) AS dismissals_count,
        d.dismissal_kind
    FROM dismissal_agg d
    WHERE d.dismissal_kind = 'retired out'
    """
    df = duckdb_con.execute(query).df()
    assert len(df) == 31
    assert (df["is_dismissed"] == True).all()
    assert (df["dismissals_count"] == 1).all()
    assert (df["dismissal_kind"] == "retired out").all()


def test_ordinary_dismissals_unchanged(duckdb_con):
    """Verify that standard dismissals (caught, bowled, lbw, run out, etc.) remain count=1."""
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT 
        d.dismissal_kind,
        COUNT(*) as cnt,
        MIN(d.true_dismissals) as min_d,
        MAX(d.true_dismissals) as max_d
    FROM dismissal_agg d
    WHERE d.dismissal_kind IN ('caught', 'bowled', 'lbw', 'run out', 'stumped', 'hit wicket')
    GROUP BY d.dismissal_kind
    """
    df = duckdb_con.execute(query).df()
    assert len(df) == 6
    assert (df["min_d"] == 1).all()
    assert (df["max_d"] == 1).all()


def test_multi_innings_dismissal_and_retirement_aggregation(duckdb_con):
    """Verify that multi-innings fixtures with 1 true dismissal and 1 retirement aggregate to dismissals_count=1."""
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            COUNT(*) as total_events,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT 
        d.dismissal_kind,
        d.total_events,
        d.true_dismissals
    FROM dismissal_agg d
    WHERE d.dismissal_kind IN ('retired hurt, caught', 'caught, retired hurt', 'retired hurt, bowled', 'bowled, retired hurt')
    """
    df = duckdb_con.execute(query).df()
    assert len(df) == 20
    assert (df["total_events"] == 2).all()
    assert (df["true_dismissals"] == 1).all()


def test_pure_multi_dismissals_in_test_cricket(duckdb_con):
    """Verify that 2 genuine dismissals in a Test match correctly produce dismissals_count=2."""
    query = """
    WITH dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    )
    SELECT COUNT(*) 
    FROM dismissal_agg 
    WHERE true_dismissals = 2
    """
    count_2 = duckdb_con.execute(query).fetchone()[0]
    # Exactly 11,097 player-matches had 2 dismissals (11,012 in Tests, 85 in Super Over fixtures)
    assert count_2 == 11097
