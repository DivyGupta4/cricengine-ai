"""
CricEngine AI — Step 4B: Feature Store Materialization Pipeline

Orchestrates the extraction, computation, validation, and materialization of
CricEngine AI's point-in-time player performance feature store:
1. Opens production DuckDB database in strict READ-ONLY mode.
2. Extracts atomic player-match box scores (200,709 records).
3. Generates match-based rolling features (L5, L10, L20).
4. Generates time-based rolling features (30d, 90d, 365d).
5. Computes expanding contextual adjustments and venue park factors.
6. Materializes Snappy-compressed Parquet datasets partitioned by format, window, and season.
7. Produces empirical baseline tables, data catalog, and global version manifest.
8. Verifies database immutability (SHA-256 and byte-size consistency).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from etl.contextual_features import (
    derive_home_away_status,
    ensure_canonical_venues_loaded,
    extract_contextual_features_dataframe,
)
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
)
from etl.rolling_features import (
    generate_rolling_match_features_df,
    generate_rolling_time_features_df,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("build_feature_store")


def calculate_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file in streaming chunks."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_player_match_dataframe(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Extract atomic player-match box scores (exact 200,709 participation grain).
    Creates a temporary table 'temp_player_match' in DuckDB for downstream rolling aggregations.
    """
    ensure_canonical_venues_loaded(con)

    query = """
    CREATE OR REPLACE TEMPORARY TABLE temp_player_match AS
    WITH 
    -- 1. Crease entry rank (batting position derivation including non-strikers & diamond ducks)
    crease_entry AS (
        SELECT 
            match_id,
            innings_num,
            batter_id AS player_id,
            MIN(over_num * 100 + delivery_num) AS first_ball_seq
        FROM fact_ball_by_ball
        GROUP BY match_id, innings_num, batter_id
        UNION ALL
        SELECT 
            b.match_id,
            b.innings_num,
            b.non_striker_id AS player_id,
            MIN(b.over_num * 100 + b.delivery_num) AS first_ball_seq
        FROM fact_ball_by_ball b
        GROUP BY b.match_id, b.innings_num, b.non_striker_id
        UNION ALL
        SELECT
            b.match_id,
            b.innings_num,
            d.player_out_id AS player_id,
            MIN(b.over_num * 100 + b.delivery_num) AS first_ball_seq
        FROM fact_delivery_dismissal d
        JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
        GROUP BY b.match_id, b.innings_num, d.player_out_id
    ),
    crease_first_seen AS (
        SELECT match_id, innings_num, player_id, MIN(first_ball_seq) AS first_ball_seq
        FROM crease_entry
        GROUP BY match_id, innings_num, player_id
    ),
    batter_ranked AS (
        SELECT 
            match_id,
            player_id,
            innings_num,
            DENSE_RANK() OVER (
                PARTITION BY match_id, innings_num 
                ORDER BY first_ball_seq ASC
            ) AS batting_pos
        FROM crease_first_seen
    ),
    batter_positions AS (
        SELECT 
            match_id,
            player_id,
            MIN(batting_pos) AS batting_position
        FROM batter_ranked
        GROUP BY match_id, player_id
    ),
    -- 2. Batting aggregates from fact_ball_by_ball
    batting_agg AS (
        SELECT 
            b.match_id,
            b.batter_id AS player_id,
            SUM(b.runs_batter) AS runs_scored,
            COUNT(CASE WHEN b.wides = 0 THEN 1 END) AS balls_faced,
            COUNT(CASE WHEN b.runs_batter = 4 THEN 1 END) AS boundary_fours,
            COUNT(CASE WHEN b.runs_batter = 6 THEN 1 END) AS boundary_sixes,
            COUNT(CASE WHEN b.runs_total = 0 AND b.wides = 0 THEN 1 END) AS dot_balls_faced
        FROM fact_ball_by_ball b
        GROUP BY b.match_id, b.batter_id
    ),
    -- 3. Dismissals from fact_delivery_dismissal (excluding non-dismissal retirements for batting average)
    dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    ),
    -- 4. Over maiden calculations
    over_maiden_calc AS (
        SELECT 
            match_id,
            innings_num,
            bowler_id,
            over_num,
            COUNT(CASE WHEN is_legal_delivery = TRUE THEN 1 END) AS legal_balls_in_over,
            SUM(runs_batter + wides + noballs) AS runs_charged_to_bowler
        FROM fact_ball_by_ball
        GROUP BY match_id, innings_num, bowler_id, over_num
    ),
    maidens_agg AS (
        SELECT 
            match_id,
            bowler_id AS player_id,
            COUNT(*) AS maiden_overs
        FROM over_maiden_calc
        WHERE legal_balls_in_over = 6 AND runs_charged_to_bowler = 0
        GROUP BY match_id, bowler_id
    ),
    -- 5. Bowling stats from fact_ball_by_ball
    bowling_balls_agg AS (
        SELECT 
            b.match_id,
            b.bowler_id AS player_id,
            COUNT(CASE WHEN b.is_legal_delivery = TRUE THEN 1 END) AS legal_balls_bowled,
            SUM(b.runs_batter + b.wides + b.noballs) AS runs_conceded,
            COUNT(CASE WHEN (b.runs_batter + b.wides + b.noballs) = 0 THEN 1 END) AS dot_balls_bowled,
            COUNT(CASE WHEN b.runs_batter IN (4, 6) THEN 1 END) AS boundaries_conceded
        FROM fact_ball_by_ball b
        GROUP BY b.match_id, b.bowler_id
    ),
    -- Bowler credited wickets from fact_delivery_dismissal joined on fact_ball_by_ball
    bowler_wickets_agg AS (
        SELECT 
            b.match_id,
            b.bowler_id AS player_id,
            COUNT(*) AS wickets_credited
        FROM fact_delivery_dismissal d
        JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
        WHERE d.bowler_credited = TRUE
        GROUP BY b.match_id, b.bowler_id
    ),
    -- 6. Fielding stats: Union outfield dismissals and caught-and-bowled fielding credit
    raw_fielding_events AS (
        SELECT 
            d.match_id,
            f.fielder_id AS player_id,
            CASE WHEN d.dismissal_kind = 'caught' THEN 1 ELSE 0 END AS is_catch,
            CASE WHEN d.dismissal_kind = 'stumped' THEN 1 ELSE 0 END AS is_stumping,
            CASE WHEN d.dismissal_kind = 'run out' THEN 1 ELSE 0 END AS is_runout
        FROM fact_dismissal_fielder f
        JOIN fact_delivery_dismissal d ON f.dismissal_id = d.dismissal_id
        
        UNION ALL
        
        SELECT 
            d.match_id,
            b.bowler_id AS player_id,
            1 AS is_catch,
            0 AS is_stumping,
            0 AS is_runout
        FROM fact_delivery_dismissal d
        JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
        WHERE d.dismissal_kind = 'caught and bowled'
    ),
    fielding_agg AS (
        SELECT 
            match_id,
            player_id,
            SUM(is_catch) AS catches_taken,
            SUM(is_stumping) AS stumpings_taken,
            SUM(is_runout) AS runouts_involved,
            COUNT(*) AS total_fielding_involvements
        FROM raw_fielding_events
        GROUP BY match_id, player_id
    ),
    -- 7. Team-level totals for load indices
    team_match_totals AS (
        SELECT 
            p.match_id,
            p.team_name,
            SUM(COALESCE(b.balls_faced, 0)) AS team_balls_faced,
            SUM(COALESCE(bw.legal_balls_bowled, 0)) AS team_legal_balls_bowled
        FROM fact_match_participation p
        LEFT JOIN batting_agg b ON p.match_id = b.match_id AND p.player_id = b.player_id
        LEFT JOIN bowling_balls_agg bw ON p.match_id = bw.match_id AND p.player_id = bw.player_id
        GROUP BY p.match_id, p.team_name
    )
    SELECT 
        p.player_id,
        p.match_id,
        m.competition_name,
        CAST(m.competition_tier AS TINYINT) AS competition_tier,
        m.match_format,
        m.season,
        m.start_date,
        COALESCE(m.match_type_number, 0) AS match_type_number,
        p.team_name,
        CASE WHEN p.team_name = m.team_1 THEN m.team_2 ELSE m.team_1 END AS opposition_team,
        c.venue_name,
        COALESCE(vm.canonical_venue_name, c.venue_name) AS canonical_venue_name,
        c.city,
        p.participation_role,
        p.in_starting_xi,
        CASE WHEN (b.player_id IS NOT NULL OR d.player_id IS NOT NULL) THEN TRUE ELSE FALSE END AS has_batted,
        CASE WHEN bw.player_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_bowled,
        CASE WHEN f.player_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_fielded,
        CASE WHEN (b.player_id IS NOT NULL OR d.player_id IS NOT NULL) THEN CAST(bp.batting_position AS TINYINT) ELSE NULL END AS batting_position,
        CASE 
            WHEN b.player_id IS NOT NULL THEN CAST(b.runs_scored AS SMALLINT)
            WHEN d.player_id IS NOT NULL THEN CAST(0 AS SMALLINT)
            ELSE NULL 
        END AS runs_scored,
        CASE 
            WHEN b.player_id IS NOT NULL THEN CAST(b.balls_faced AS SMALLINT)
            WHEN d.player_id IS NOT NULL THEN CAST(0 AS SMALLINT)
            ELSE NULL 
        END AS balls_faced,
        CASE 
            WHEN b.player_id IS NOT NULL THEN CAST(b.boundary_fours AS TINYINT)
            WHEN d.player_id IS NOT NULL THEN CAST(0 AS TINYINT)
            ELSE NULL 
        END AS boundary_fours,
        CASE 
            WHEN b.player_id IS NOT NULL THEN CAST(b.boundary_sixes AS TINYINT)
            WHEN d.player_id IS NOT NULL THEN CAST(0 AS TINYINT)
            ELSE NULL 
        END AS boundary_sixes,
        CASE 
            WHEN b.player_id IS NOT NULL THEN CAST(b.dot_balls_faced AS SMALLINT)
            WHEN d.player_id IS NOT NULL THEN CAST(0 AS SMALLINT)
            ELSE NULL 
        END AS dot_balls_faced,
        CASE 
            WHEN COALESCE(d.true_dismissals, 0) > 0 THEN TRUE 
            ELSE FALSE 
        END AS is_dismissed,
        CAST(COALESCE(d.true_dismissals, 0) AS TINYINT) AS dismissals_count,
        d.dismissal_kind,
        ROUND(CASE WHEN b.balls_faced > 0 THEN (b.runs_scored * 100.0) / b.balls_faced ELSE NULL END, 2) AS strike_rate,
        ROUND(CASE WHEN b.balls_faced > 0 THEN ((b.boundary_fours + b.boundary_sixes) * 100.0) / b.balls_faced ELSE NULL END, 2) AS boundary_pct,
        ROUND(CASE WHEN b.balls_faced > 0 THEN (b.dot_balls_faced * 100.0) / b.balls_faced ELSE NULL END, 2) AS dot_pct_faced,
        CAST(bw.legal_balls_bowled AS SMALLINT) AS legal_balls_bowled,
        ROUND(bw.legal_balls_bowled / 6.0, 1) AS overs_bowled,
        CAST(bw.runs_conceded AS SMALLINT) AS runs_conceded,
        CASE WHEN bw.player_id IS NOT NULL THEN CAST(COALESCE(w.wickets_credited, 0) AS TINYINT) ELSE NULL END AS wickets_credited,
        CAST(bw.dot_balls_bowled AS SMALLINT) AS dot_balls_bowled,
        CAST(bw.boundaries_conceded AS SMALLINT) AS boundaries_conceded,
        CASE WHEN bw.player_id IS NOT NULL THEN CAST(COALESCE(md.maiden_overs, 0) AS TINYINT) ELSE NULL END AS maiden_overs,
        ROUND(CASE WHEN bw.legal_balls_bowled > 0 THEN (bw.runs_conceded * 6.0) / bw.legal_balls_bowled ELSE NULL END, 2) AS economy_rate,
        ROUND(CASE WHEN COALESCE(w.wickets_credited, 0) > 0 THEN (bw.legal_balls_bowled * 1.0) / w.wickets_credited ELSE NULL END, 2) AS bowling_strike_rate,
        ROUND(CASE WHEN COALESCE(w.wickets_credited, 0) > 0 THEN (bw.runs_conceded * 1.0) / w.wickets_credited ELSE NULL END, 2) AS bowling_average,
        CASE WHEN (f.player_id IS NOT NULL OR p.fielded_flag = TRUE) THEN CAST(COALESCE(f.catches_taken, 0) AS TINYINT) ELSE NULL END AS catches_taken,
        CASE WHEN (f.player_id IS NOT NULL OR p.fielded_flag = TRUE) THEN CAST(COALESCE(f.stumpings_taken, 0) AS TINYINT) ELSE NULL END AS stumpings_taken,
        CASE WHEN (f.player_id IS NOT NULL OR p.fielded_flag = TRUE) THEN CAST(COALESCE(f.runouts_involved, 0) AS TINYINT) ELSE NULL END AS runouts_involved,
        CASE WHEN (f.player_id IS NOT NULL OR p.fielded_flag = TRUE) THEN CAST(COALESCE(f.total_fielding_involvements, 0) AS TINYINT) ELSE NULL END AS total_fielding_involvements,
        ROUND(CASE WHEN tmt.team_balls_faced > 0 THEN COALESCE(b.balls_faced, 0) * 1.0 / tmt.team_balls_faced ELSE 0.0 END, 4) AS batting_load,
        ROUND(CASE WHEN tmt.team_legal_balls_bowled > 0 THEN COALESCE(bw.legal_balls_bowled, 0) * 1.0 / tmt.team_legal_balls_bowled ELSE 0.0 END, 4) AS bowling_load,
        ROUND(
            CASE 
                WHEN (COALESCE(b.balls_faced, 0) > 0 AND COALESCE(bw.legal_balls_bowled, 0) > 0) THEN 
                    (2.0 * (COALESCE(b.balls_faced, 0) * 1.0 / NULLIF(tmt.team_balls_faced, 0)) * (COALESCE(bw.legal_balls_bowled, 0) * 1.0 / NULLIF(tmt.team_legal_balls_bowled, 0))) /
                    ((COALESCE(b.balls_faced, 0) * 1.0 / NULLIF(tmt.team_balls_faced, 0)) + (COALESCE(bw.legal_balls_bowled, 0) * 1.0 / NULLIF(tmt.team_legal_balls_bowled, 0)) + 0.000001)
                ELSE 0.0 
            END, 4
        ) AS allrounder_balance_index
    FROM fact_match_participation p
    JOIN dim_match m ON p.match_id = m.match_id
    JOIN dim_match_context c ON m.match_id = c.match_id
    LEFT JOIN temp_venue_mapping vm ON c.venue_name = vm.raw_venue_name
    LEFT JOIN batter_positions bp ON p.match_id = bp.match_id AND p.player_id = bp.player_id
    LEFT JOIN batting_agg b ON p.match_id = b.match_id AND p.player_id = b.player_id
    LEFT JOIN dismissal_agg d ON p.match_id = d.match_id AND p.player_id = d.player_id
    LEFT JOIN bowling_balls_agg bw ON p.match_id = bw.match_id AND p.player_id = bw.player_id
    LEFT JOIN bowler_wickets_agg w ON p.match_id = w.match_id AND p.player_id = w.player_id
    LEFT JOIN maidens_agg md ON p.match_id = md.match_id AND p.player_id = md.player_id
    LEFT JOIN fielding_agg f ON p.match_id = f.match_id AND p.player_id = f.player_id
    LEFT JOIN team_match_totals tmt ON p.match_id = tmt.match_id AND p.team_name = tmt.team_name;
    """
    logger.info("Extracting atomic player-match records and staging in temp_player_match...")
    con.execute(query)
    
    # Return dataframe matching the PLAYER_MATCH_SCHEMA fields
    cols = [field.name for field in PLAYER_MATCH_SCHEMA]
    select_cols = ", ".join(cols)
    df = con.execute(f"SELECT {select_cols} FROM temp_player_match").df()
    logger.info("Extracted %d player-match records across %d fields.", len(df), len(cols))
    return df


def write_partitioned_dataset(
    df: pd.DataFrame,
    schema: pa.Schema,
    partition_cols: List[str],
    output_path: Path,
) -> None:
    """Write DataFrame as partitioned Snappy-compressed Parquet dataset."""
    output_path.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_to_dataset(
        table,
        root_path=str(output_path),
        partition_cols=partition_cols,
        compression="SNAPPY",
        use_dictionary=True,
    )
    logger.info("Successfully materialized %d records to %s", len(df), output_path)


def generate_and_materialize_baselines(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
) -> Dict[str, int]:
    """Generate empirical ground, phase, and opposition baselines."""
    ensure_canonical_venues_loaded(con)
    baselines_dir = output_dir / "contextual_baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    baseline_counts = {}

    # 1. Venue Park Factors (using canonical ground names)
    q_venue = """
    WITH venue_format_runs AS (
        SELECT 
            COALESCE(vm.canonical_venue_name, c.venue_name) AS canonical_venue_name,
            m.match_format,
            COUNT(DISTINCT m.match_id) AS total_matches,
            SUM(b.runs_total) AS total_runs,
            COUNT(CASE WHEN b.is_legal_delivery = TRUE THEN 1 END) AS total_legal_balls
        FROM dim_match m
        JOIN dim_match_context c ON m.match_id = c.match_id
        LEFT JOIN temp_venue_mapping vm ON c.venue_name = vm.raw_venue_name
        JOIN fact_ball_by_ball b ON m.match_id = b.match_id
        GROUP BY COALESCE(vm.canonical_venue_name, c.venue_name), m.match_format
    ),
    format_runs AS (
        SELECT 
            match_format,
            SUM(total_runs) AS format_total_runs,
            SUM(total_legal_balls) AS format_total_legal_balls
        FROM venue_format_runs
        GROUP BY match_format
    )
    SELECT 
        v.canonical_venue_name,
        v.match_format,
        v.total_matches,
        v.total_runs,
        v.total_legal_balls,
        ROUND((v.total_runs * 1.0 / NULLIF(v.total_legal_balls, 0)) / 
              (f.format_total_runs * 1.0 / NULLIF(f.format_total_legal_balls, 0)), 4) AS park_factor
    FROM venue_format_runs v
    JOIN format_runs f ON v.match_format = f.match_format
    ORDER BY v.match_format, v.total_matches DESC
    """
    df_venue = con.execute(q_venue).df()
    pq.write_table(pa.Table.from_pandas(df_venue), baselines_dir / "venue_park_factors.parquet", compression="SNAPPY")
    baseline_counts["venue_park_factors"] = len(df_venue)

    # 2. Match Phase Baselines
    q_phase = """
    SELECT 
        m.match_format,
        b.match_phase,
        COUNT(*) AS total_balls,
        COUNT(CASE WHEN b.is_legal_delivery = TRUE THEN 1 END) AS total_legal_balls,
        SUM(b.runs_total) AS total_runs,
        SUM(CASE WHEN b.is_wicket = TRUE THEN 1 ELSE 0 END) AS total_wickets,
        ROUND(SUM(b.runs_total) * 6.0 / NULLIF(COUNT(CASE WHEN b.is_legal_delivery = TRUE THEN 1 END), 0), 2) AS runs_per_over,
        ROUND(COUNT(CASE WHEN b.runs_batter IN (4, 6) THEN 1 END) * 100.0 / COUNT(*), 2) AS boundary_pct,
        ROUND(COUNT(CASE WHEN b.runs_total = 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS dot_pct
    FROM dim_match m
    JOIN fact_ball_by_ball b ON m.match_id = b.match_id
    GROUP BY m.match_format, b.match_phase
    ORDER BY m.match_format, b.match_phase
    """
    df_phase = con.execute(q_phase).df()
    pq.write_table(pa.Table.from_pandas(df_phase), baselines_dir / "phase_scoring_baselines.parquet", compression="SNAPPY")
    baseline_counts["phase_scoring_baselines"] = len(df_phase)

    # 3. Opposition Bowling Unit Baselines
    q_opp_bowl = """
    SELECT 
        m.match_format,
        i.bowling_team AS team_name,
        COUNT(DISTINCT m.match_id) AS total_matches,
        SUM(i.total_legal_deliveries) AS total_legal_deliveries,
        SUM(i.total_runs_scored) AS total_runs_conceded,
        SUM(i.total_wickets_lost) AS total_wickets_taken,
        ROUND(SUM(i.total_runs_scored) * 6.0 / NULLIF(SUM(i.total_legal_deliveries), 0), 2) AS team_economy_rate,
        ROUND(SUM(i.total_runs_scored) * 1.0 / NULLIF(SUM(i.total_wickets_lost), 0), 2) AS team_bowling_average
    FROM dim_match m
    JOIN fact_innings i ON m.match_id = i.match_id
    GROUP BY m.match_format, i.bowling_team
    ORDER BY m.match_format, total_matches DESC
    """
    df_opp_bowl = con.execute(q_opp_bowl).df()
    pq.write_table(pa.Table.from_pandas(df_opp_bowl), baselines_dir / "opposition_bowling_baselines.parquet", compression="SNAPPY")
    baseline_counts["opposition_bowling_baselines"] = len(df_opp_bowl)

    # 4. Opposition Batting Unit Baselines
    q_opp_bat = """
    SELECT 
        m.match_format,
        i.batting_team AS team_name,
        COUNT(DISTINCT m.match_id) AS total_matches,
        SUM(i.total_legal_deliveries) AS total_legal_deliveries,
        SUM(i.total_runs_scored) AS total_runs_scored,
        SUM(i.total_wickets_lost) AS total_wickets_lost,
        ROUND(SUM(i.total_runs_scored) * 6.0 / NULLIF(SUM(i.total_legal_deliveries), 0), 2) AS team_scoring_rate,
        ROUND(SUM(i.total_runs_scored) * 1.0 / NULLIF(SUM(i.total_wickets_lost), 0), 2) AS team_batting_average
    FROM dim_match m
    JOIN fact_innings i ON m.match_id = i.match_id
    GROUP BY m.match_format, i.batting_team
    ORDER BY m.match_format, total_matches DESC
    """
    df_opp_bat = con.execute(q_opp_bat).df()
    pq.write_table(pa.Table.from_pandas(df_opp_bat), baselines_dir / "opposition_batting_baselines.parquet", compression="SNAPPY")
    baseline_counts["opposition_batting_baselines"] = len(df_opp_bat)

    logger.info("Contextual baselines materialized: %s", baseline_counts)
    return baseline_counts


def write_feature_metadata(output_dir: Path) -> None:
    """Write catalog and lineage definitions to feature_metadata/."""
    meta_dir = output_dir / "feature_metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    catalog = {
        "catalog_version": "1.0.0",
        "description": "CricEngine AI Point-in-Time Feature Store Data Catalog",
        "schemas": {
            "player_match": {
                "description": "Atomic match box score features per player-match participation",
                "columns": {f.name: str(f.type) for f in PLAYER_MATCH_SCHEMA},
            },
            "rolling_match": {
                "description": "Match-based rolling window performance aggregations (L5, L10, L20)",
                "columns": {f.name: str(f.type) for f in ROLLING_MATCH_SCHEMA},
            },
            "rolling_time": {
                "description": "Time-based rolling window performance aggregations (30d, 90d, 365d)",
                "columns": {f.name: str(f.type) for f in ROLLING_TIME_SCHEMA},
            },
            "contextual_features": {
                "description": "Non-circular point-in-time contextual features and adjustments",
                "columns": {f.name: str(f.type) for f in CONTEXTUAL_FEATURES_SCHEMA},
            },
        },
        "format_parameters": {
            "half_lives_days": FORMAT_HALF_LIVES_DAYS,
            "min_sample_requirements": MIN_SAMPLE_REQUIREMENTS,
        },
    }

    lineage = {
        "lineage_version": "1.0.0",
        "source": "data/datalake/curated/cricengine.duckdb",
        "pipeline": [
            {
                "step": "player_match_extraction",
                "inputs": ["fact_match_participation", "dim_match", "dim_match_context", "fact_ball_by_ball", "fact_delivery_dismissal", "fact_dismissal_fielder"],
                "target": "data/datalake/feature_store/player_match",
            },
            {
                "step": "rolling_match_features",
                "inputs": ["temp_player_match"],
                "windows": MATCH_WINDOWS,
                "target": "data/datalake/feature_store/rolling_match",
            },
            {
                "step": "rolling_time_features",
                "inputs": ["temp_player_match"],
                "windows_days": TIME_WINDOWS_DAYS,
                "target": "data/datalake/feature_store/rolling_time",
            },
            {
                "step": "contextual_features",
                "inputs": ["fact_match_participation", "dim_match", "fact_innings", "fact_ball_by_ball"],
                "target": "data/datalake/feature_store/contextual_features",
            },
        ],
    }

    with open(meta_dir / "feature_catalog_v1.json", "w") as f:
        json.dump(catalog, f, indent=2)

    with open(meta_dir / "transformation_lineage.json", "w") as f:
        json.dump(lineage, f, indent=2)

    logger.info("Feature metadata written to %s", meta_dir)


def write_feature_store_manifest(
    output_dir: Path,
    db_sha256: str,
    db_size_bytes: int,
    dataset_metrics: Dict[str, Any],
) -> None:
    """Write root _manifest.json recording dataset schemas, row counts, and source lineage."""
    manifest_data = {
        "feature_store_version": "3.0.0-phase3a",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_database": {
            "path": "data/datalake/curated/cricengine.duckdb",
            "sha256": db_sha256,
            "size_bytes": db_size_bytes,
        },
        "compression": "SNAPPY",
        "formats_supported": FORMATS,
        "match_windows": MATCH_WINDOWS,
        "time_windows_days": TIME_WINDOWS_DAYS,
        "datasets": dataset_metrics,
        "zero_conflation_policy": "Strict. Did not bat / did not bowl emit NULL, never zero.",
        "leakage_prevention": "Evaluated match strictly excluded from rolling window frames.",
    }

    manifest_path = output_dir / "_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
    logger.info("Global version manifest written to %s", manifest_path)


def build_feature_store(db_path: Path, output_dir: Path) -> Dict[str, Any]:
    """Execute complete end-to-end feature store materialization."""
    start_total_time = time.time()
    logger.info("=================================================================")
    logger.info("CricEngine AI — Step 4B: Feature Store Pipeline Initialization")
    logger.info("=================================================================")
    logger.info("Curated Database Path: %s", db_path)
    logger.info("Feature Store Target:  %s", output_dir)

    if not db_path.exists():
        raise FileNotFoundError(f"Curated database not found at {db_path}")

    # Compute pre-run SHA-256 and byte size
    logger.info("Computing pre-run database checksum...")
    initial_sha256 = calculate_file_sha256(db_path)
    initial_size = db_path.stat().st_size
    logger.info("Pre-run DuckDB SHA-256: %s", initial_sha256)
    logger.info("Pre-run DuckDB Size:    %d bytes (%.2f MB)", initial_size, initial_size / (1024 * 1024))

    # Connect strictly in read-only mode
    con = duckdb.connect(str(db_path), read_only=True)
    dataset_metrics = {}

    try:
        # Step 1: Extract and Materialize player_match
        logger.info("\n--- Phase 1: Materializing player_match ---")
        t0 = time.time()
        df_pm = extract_player_match_dataframe(con)
        pm_path = output_dir / "player_match"
        if pm_path.exists():
            import shutil
            shutil.rmtree(pm_path)
        write_partitioned_dataset(
            df_pm,
            PLAYER_MATCH_SCHEMA,
            partition_cols=["match_format", "season"],
            output_path=pm_path,
        )
        dataset_metrics["player_match"] = {
            "row_count": len(df_pm),
            "columns": len(PLAYER_MATCH_SCHEMA),
            "duration_seconds": round(time.time() - t0, 2),
            "partitions": ["match_format", "season"],
        }

        # Step 2: Compute and Materialize rolling_match for N in [5, 10, 20]
        logger.info("\n--- Phase 2: Materializing rolling_match (L5, L10, L20) ---")
        rm_path = output_dir / "rolling_match"
        if rm_path.exists():
            import shutil
            shutil.rmtree(rm_path)
        rolling_match_metrics = {}
        total_rm_rows = 0
        t_rm_start = time.time()
        for window in MATCH_WINDOWS:
            t0 = time.time()
            logger.info("Computing rolling match window N=%d...", window)
            df_rm = generate_rolling_match_features_df(con, "temp_player_match", window)
            write_partitioned_dataset(
                df_rm,
                ROLLING_MATCH_SCHEMA,
                partition_cols=["match_format", "window_size", "season"],
                output_path=rm_path,
            )
            rolling_match_metrics[f"window_{window}"] = {
                "row_count": len(df_rm),
                "duration_seconds": round(time.time() - t0, 2),
            }
            total_rm_rows += len(df_rm)

        dataset_metrics["rolling_match"] = {
            "total_row_count": total_rm_rows,
            "columns": len(ROLLING_MATCH_SCHEMA),
            "windows": MATCH_WINDOWS,
            "duration_seconds": round(time.time() - t_rm_start, 2),
            "partitions": ["match_format", "window_size", "season"],
            "window_breakdown": rolling_match_metrics,
        }

        # Step 3: Compute and Materialize rolling_time for T in [30, 90, 365]
        logger.info("\n--- Phase 3: Materializing rolling_time (30d, 90d, 365d) ---")
        rt_path = output_dir / "rolling_time"
        if rt_path.exists():
            import shutil
            shutil.rmtree(rt_path)
        rolling_time_metrics = {}
        total_rt_rows = 0
        t_rt_start = time.time()
        for window_days in TIME_WINDOWS_DAYS:
            t0 = time.time()
            logger.info("Computing rolling time window T=%d days...", window_days)
            df_rt = generate_rolling_time_features_df(con, "temp_player_match", window_days)
            write_partitioned_dataset(
                df_rt,
                ROLLING_TIME_SCHEMA,
                partition_cols=["match_format", "window_days", "season"],
                output_path=rt_path,
            )
            rolling_time_metrics[f"days_{window_days}"] = {
                "row_count": len(df_rt),
                "duration_seconds": round(time.time() - t0, 2),
            }
            total_rt_rows += len(df_rt)

        dataset_metrics["rolling_time"] = {
            "total_row_count": total_rt_rows,
            "columns": len(ROLLING_TIME_SCHEMA),
            "windows_days": TIME_WINDOWS_DAYS,
            "duration_seconds": round(time.time() - t_rt_start, 2),
            "partitions": ["match_format", "window_days", "season"],
            "window_breakdown": rolling_time_metrics,
        }

        # Step 4: Compute and Materialize contextual_features
        logger.info("\n--- Phase 4: Materializing contextual_features ---")
        t0 = time.time()
        df_ctx = extract_contextual_features_dataframe(con)
        ctx_path = output_dir / "contextual_features"
        if ctx_path.exists():
            import shutil
            shutil.rmtree(ctx_path)
        write_partitioned_dataset(
            df_ctx,
            CONTEXTUAL_FEATURES_SCHEMA,
            partition_cols=["match_format", "season"],
            output_path=ctx_path,
        )
        dataset_metrics["contextual_features"] = {
            "row_count": len(df_ctx),
            "columns": len(CONTEXTUAL_FEATURES_SCHEMA),
            "duration_seconds": round(time.time() - t0, 2),
            "partitions": ["match_format", "season"],
        }

        # Step 5: Materialize empirical baselines
        logger.info("\n--- Phase 5: Generating Contextual Baselines ---")
        baselines = generate_and_materialize_baselines(con, output_dir)
        dataset_metrics["contextual_baselines"] = baselines

        # Step 6: Metadata & Manifest
        logger.info("\n--- Phase 6: Emitting Metadata and Manifest ---")
        write_feature_metadata(output_dir)
        write_feature_store_manifest(output_dir, initial_sha256, initial_size, dataset_metrics)

    finally:
        con.close()
        logger.info("Closed read-only DuckDB connection.")

    # Post-run Database Immutability Check
    logger.info("\n--- Verifying Curated Database Immutability ---")
    post_sha256 = calculate_file_sha256(db_path)
    post_size = db_path.stat().st_size
    logger.info("Post-run DuckDB SHA-256: %s", post_sha256)
    logger.info("Post-run DuckDB Size:    %d bytes (%.2f MB)", post_size, post_size / (1024 * 1024))

    assert initial_sha256 == post_sha256, f"FATAL: Database checksum changed! {initial_sha256} != {post_sha256}"
    assert initial_size == post_size, f"FATAL: Database size changed! {initial_size} != {post_size}"
    logger.info("DATABASE IMMUTABILITY VERIFIED: Checksum and byte size are 100%% identical.")

    total_elapsed = time.time() - start_total_time
    logger.info("\n=================================================================")
    logger.info("CricEngine AI Feature Store Materialization Completed Successfully!")
    logger.info("Total Pipeline Duration: %.2f seconds", total_elapsed)
    logger.info("=================================================================")
    return dataset_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="CricEngine AI Feature Store Materialization")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/datalake/curated/cricengine.duckdb"),
        help="Path to curated DuckDB database",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/datalake/feature_store_v3a"),
        help="Destination directory for feature store Parquet artifacts",
    )
    args = parser.parse_args()
    build_feature_store(args.db_path, args.output_dir)


if __name__ == "__main__":
    main()
