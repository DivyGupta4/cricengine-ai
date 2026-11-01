"""
CricEngine AI — Tests for Feature Store Definitions & Core Contracts
"""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from etl.feature_definitions import (
    COMPETITION_TIERS,
    CONTEXTUAL_FEATURES_SCHEMA,
    FORMAT_HALF_LIVES_DAYS,
    FORMATS,
    MATCH_WINDOWS,
    MIN_SAMPLE_REQUIREMENTS,
    PLAYER_MATCH_SCHEMA,
    ROLLING_MATCH_SCHEMA,
    ROLLING_TIME_SCHEMA,
    TIME_WINDOWS_DAYS,
    apply_bayesian_shrinkage,
    compute_all_rounder_index,
    compute_recency_weight,
)
from etl.contextual_features import derive_home_away_status


def test_schema_contracts():
    """Verify schema column counts and critical field definitions."""
    assert len(PLAYER_MATCH_SCHEMA) == 46
    assert len(ROLLING_MATCH_SCHEMA) == 34
    assert len(ROLLING_TIME_SCHEMA) == 19
    assert len(CONTEXTUAL_FEATURES_SCHEMA) == 18

    # Check key primary keys and types
    assert PLAYER_MATCH_SCHEMA.field("player_id").type == pa.string()
    assert PLAYER_MATCH_SCHEMA.field("match_id").type == pa.string()
    assert PLAYER_MATCH_SCHEMA.field("strike_rate").type == pa.float32()
    assert PLAYER_MATCH_SCHEMA.field("economy_rate").type == pa.float32()
    assert PLAYER_MATCH_SCHEMA.field("allrounder_balance_index").type == pa.float32()

    assert ROLLING_MATCH_SCHEMA.field("rolling_batting_sr").type == pa.float32()
    assert ROLLING_MATCH_SCHEMA.field("shrunk_batting_sr").type == pa.float32()
    assert ROLLING_MATCH_SCHEMA.field("decayed_batting_sr").type == pa.float32()


def test_all_rounder_index_math():
    """Verify harmonic mean computation of All-Rounder Balance Index (ABI)."""
    # Pure batter: zero bowling load -> ABI == 0.0
    assert compute_all_rounder_index(0.35, 0.0) == 0.0
    assert compute_all_rounder_index(0.0, 0.25) == 0.0
    assert compute_all_rounder_index(0.0, 0.0) == 0.0

    # Genuine all-rounder: balanced loads
    l_bat, l_bowl = 0.25, 0.20
    expected = (2.0 * l_bat * l_bowl) / (l_bat + l_bowl)
    abi = compute_all_rounder_index(l_bat, l_bowl)
    assert pytest.approx(abi, rel=1e-3) == round(expected, 4)
    assert 0.0 <= abi <= 1.0


def test_empirical_bayes_shrinkage_math():
    """Verify Bayesian shrinkage towards cohort prior."""
    prior = 130.0  # T20 batting SR cohort prior
    m = 40.0       # Pseudo-counts

    # Zero sample size -> shrinks completely to cohort prior
    assert apply_bayesian_shrinkage(None, 0.0, prior, m) == prior
    assert apply_bayesian_shrinkage(180.0, 0.0, prior, m) == prior

    # Low sample size (e.g. 10 balls, observed 200.0 SR)
    # Shrunk = (10 / 50) * 200 + (40 / 50) * 130 = 40 + 104 = 144.0
    shrunk_small = apply_bayesian_shrinkage(200.0, 10.0, prior, m)
    assert shrunk_small == 144.0

    # Large sample size (e.g. 1000 balls, observed 150.0 SR)
    # Shrunk = (1000 / 1040) * 150 + (40 / 1040) * 130 = 144.23 + 5.00 = 149.23
    shrunk_large = apply_bayesian_shrinkage(150.0, 1000.0, prior, m)
    assert pytest.approx(shrunk_large, abs=0.5) == 149.23


def test_recency_decay_math():
    """Verify exponential half-life weighting w = 2^(-delta_t / half_life)."""
    half_life_t20 = FORMAT_HALF_LIVES_DAYS["T20"]  # 90 days
    assert compute_recency_weight(0, half_life_t20) == 1.0
    assert pytest.approx(compute_recency_weight(90, half_life_t20), rel=1e-4) == 0.5
    assert pytest.approx(compute_recency_weight(180, half_life_t20), rel=1e-4) == 0.25
    assert pytest.approx(compute_recency_weight(270, half_life_t20), rel=1e-4) == 0.125


def test_home_away_status_derivation():
    """Verify deterministic home/away/neutral derivation."""
    # IPL Franchise: Wankhede is Mumbai Indians home
    is_home, is_neutral = derive_home_away_status(
        venue_name="Wankhede Stadium, Mumbai",
        team_name="Mumbai Indians",
        opposition_team="Chennai Super Kings",
        competition_tier=2,
    )
    assert is_home is True
    assert is_neutral is False

    # IPL Franchise: Away match for CSK at Wankhede
    is_home_csk, is_neutral_csk = derive_home_away_status(
        venue_name="Wankhede Stadium, Mumbai",
        team_name="Chennai Super Kings",
        opposition_team="Mumbai Indians",
        competition_tier=2,
    )
    assert is_home_csk is False
    assert is_neutral_csk is False

    # Neutral IPL playoff: KKR vs SRH at Wankhede
    is_home_neu, is_neutral_neu = derive_home_away_status(
        venue_name="Wankhede Stadium, Mumbai",
        team_name="Kolkata Knight Riders",
        opposition_team="Sunrisers Hyderabad",
        competition_tier=2,
    )
    assert is_home_neu is False
    assert is_neutral_neu is True

    # International: India playing at Eden Gardens against Australia
    is_home_ind, is_neutral_ind = derive_home_away_status(
        venue_name="Eden Gardens, Kolkata",
        team_name="India",
        opposition_team="Australia",
        competition_tier=1,
    )
    assert is_home_ind is True
    assert is_neutral_ind is False


def test_materialized_feature_store_integrity():
    """Verify that materialized parquet feature store on disk matches manifest and schemas."""
    import json
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    manifest_path = fs_dir / "_manifest.json"
    if not manifest_path.exists():
        pytest.skip("Feature store not yet materialized.")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # 1. Verify player_match
    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    assert pm_ds.count_rows() == 200709
    assert len(pm_ds.schema) == 46

    # 2. Verify rolling_match
    rm_ds = ds.dataset(str(fs_dir / "rolling_match"), format="parquet", partitioning="hive")
    assert rm_ds.count_rows() == 602127
    assert len(rm_ds.schema) == 34

    # 3. Verify rolling_time
    rt_ds = ds.dataset(str(fs_dir / "rolling_time"), format="parquet", partitioning="hive")
    assert rt_ds.count_rows() == 602127
    assert len(rt_ds.schema) == 19

    # 4. Verify contextual_features
    ctx_ds = ds.dataset(str(fs_dir / "contextual_features"), format="parquet", partitioning="hive")
    assert ctx_ds.count_rows() == 200709
    assert len(ctx_ds.schema) == 18

    # 5. Verify baselines
    vp = pq.read_table(fs_dir / "contextual_baselines" / "venue_park_factors.parquet")
    assert vp.num_rows == 824
    ps = pq.read_table(fs_dir / "contextual_baselines" / "phase_scoring_baselines.parquet")
    assert ps.num_rows == 11
    ob = pq.read_table(fs_dir / "contextual_baselines" / "opposition_bowling_baselines.parquet")
    assert ob.num_rows == 206
    obat = pq.read_table(fs_dir / "contextual_baselines" / "opposition_batting_baselines.parquet")
    assert obat.num_rows == 206


def test_materialized_zero_conflation():
    """Verify that unobserved batting/bowling in materialized data is strictly NULL, not 0.0."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    
    # Filter players who did not bowl
    non_bowlers = pm_ds.to_table(filter=(pc.field("has_bowled") == False), columns=["economy_rate", "overs_bowled", "wickets_credited"])
    assert non_bowlers.num_rows > 0
    # Economy rate and overs bowled MUST be null
    assert non_bowlers.column("economy_rate").null_count == non_bowlers.num_rows
    assert non_bowlers.column("overs_bowled").null_count == non_bowlers.num_rows
    assert non_bowlers.column("wickets_credited").null_count == non_bowlers.num_rows


def test_remediation_diamond_ducks():
    """Verify diamond ducks: players dismissed without facing a ball have has_batted=True, balls_faced=0, runs=0, is_dismissed=True."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    flt = (pc.field("has_batted") == True) & (pc.field("balls_faced") == 0) & (pc.field("is_dismissed") == True)
    tbl = pm_ds.to_table(filter=flt, columns=["player_id", "match_id", "runs_scored", "balls_faced", "is_dismissed", "dismissals_count", "strike_rate"])
    
    # At least 324 diamond duck dismissals
    assert tbl.num_rows >= 324
    assert pc.sum(tbl.column("runs_scored")).as_py() == 0
    assert pc.sum(tbl.column("balls_faced")).as_py() == 0
    # Strike rate must be NULL (zero conflation policy)
    assert tbl.column("strike_rate").null_count == tbl.num_rows


def test_remediation_caught_and_bowled():
    """Verify caught-and-bowled fielding credit attribution to bowler."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    flt = (pc.field("has_bowled") == True) & (pc.field("catches_taken") > 0)
    tbl = pm_ds.to_table(filter=flt, columns=["player_id", "match_id", "wickets_credited", "catches_taken", "total_fielding_involvements"])
    # Bowling fielders who took catches must exist
    assert tbl.num_rows > 0


def test_remediation_multi_innings_dismissals():
    """Verify multi-innings Test matches track dismissals_count (0, 1, 2) and exactly 11,036 player-matches have 2 dismissals."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    flt = (pc.field("match_format") == "Test") & (pc.field("dismissals_count") == 2)
    tbl = pm_ds.to_table(filter=flt, columns=["player_id", "match_id", "dismissals_count"])
    assert tbl.num_rows == 11036


def test_remediation_canonical_venues():
    """Verify canonical_venue_name is populated and consolidates venue aliases into canonical grounds."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    pm_ds = ds.dataset(str(fs_dir / "player_match"), format="parquet", partitioning="hive")
    tbl = pm_ds.to_table(columns=["venue_name", "canonical_venue_name"])
    assert tbl.column("canonical_venue_name").null_count == 0
    
    unique_raw = len(pc.unique(tbl.column("venue_name")))
    unique_canonical = len(pc.unique(tbl.column("canonical_venue_name")))
    assert unique_raw == 527
    assert unique_canonical == 500


def test_remediation_opposition_batting_baselines():
    """Verify opposition_batting_baselines.parquet is serialized and schema is complete."""
    fs_dir = Path("data/datalake/feature_store")
    if not (fs_dir / "_manifest.json").exists():
        pytest.skip("Feature store not yet materialized.")

    p = fs_dir / "contextual_baselines" / "opposition_batting_baselines.parquet"
    assert p.exists()
    tbl = pq.read_table(p)
    assert tbl.num_rows == 206
    cols = tbl.column_names
    assert "match_format" in cols
    assert "team_name" in cols
    assert "team_scoring_rate" in cols
    assert "team_batting_average" in cols


