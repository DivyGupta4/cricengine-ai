"""
CricEngine AI — Phase 3B: Feature Store Materialization Pipeline (v3.1.0-phase3b)
Materializes the enriched point-in-time feature store in data/datalake/feature_store_v3b/
incorporating corrected participation rosters and enriched player attributes.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import shutil
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
logger = logging.getLogger("build_feature_store_v3b")

FEATURE_STORE_VERSION_V3B = "3.1.0-phase3b"

# Extended Schema for player_match in Phase 3B (51 columns)
PLAYER_MATCH_SCHEMA_V3B = pa.schema([
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
    ("batting_hand", pa.string()),
    ("bowling_style", pa.string()),
    ("pace_spin_class", pa.string()),
    ("primary_role", pa.string()),
    ("player_age_at_match", pa.float32()),
])


def calculate_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file in streaming chunks."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_partitioned_dataset(
    df: pd.DataFrame,
    schema: pa.Schema,
    partition_cols: List[str],
    output_path: Path,
) -> None:
    """Write DataFrame as partitioned Snappy-compressed Parquet dataset matching exact schema."""
    output_path.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(output_path),
        partition_cols=partition_cols,
        compression="SNAPPY",
        use_dictionary=True,
    )


def extract_player_match_dataframe_v3b(
    con: duckdb.DuckDBPyConnection,
    part_v3b_parquet: Path,
    enriched_master_parquet: Path,
) -> pd.DataFrame:
    """Extract player-match records enriched with Phase 3B attributes and corrected participation."""
    ensure_canonical_venues_loaded(con)

    # Register temporary tables from Phase 3B parquet outputs
    con.execute(f"CREATE OR REPLACE TEMPORARY TABLE temp_part_v3b AS SELECT * FROM read_parquet('{part_v3b_parquet}')")
    con.execute(f"CREATE OR REPLACE TEMPORARY TABLE temp_master_enriched AS SELECT * FROM read_parquet('{enriched_master_parquet}')")

    query = """
    CREATE OR REPLACE TEMPORARY TABLE temp_player_match AS
    WITH 
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
    dismissal_agg AS (
        SELECT 
            match_id,
            player_out_id AS player_id,
            COUNT(CASE WHEN dismissal_kind NOT IN ('retired hurt', 'retired not out') THEN 1 END) AS true_dismissals,
            STRING_AGG(dismissal_kind, ', ') AS dismissal_kind
        FROM fact_delivery_dismissal
        GROUP BY match_id, player_out_id
    ),
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
    team_match_totals AS (
        SELECT 
            p.match_id,
            p.team_name,
            SUM(COALESCE(b.balls_faced, 0)) AS team_balls_faced,
            SUM(COALESCE(bw.legal_balls_bowled, 0)) AS team_legal_balls_bowled
        FROM temp_part_v3b p
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
        ) AS allrounder_balance_index,
        -- Phase 3B Enriched Attributes
        pme.batting_hand,
        pme.bowling_style,
        pme.pace_spin_class,
        pme.current_role AS primary_role,
        CASE 
            WHEN pme.date_of_birth IS NOT NULL THEN 
                CAST(ROUND(date_diff('day', CAST(pme.date_of_birth AS DATE), m.start_date) / 365.25, 2) AS FLOAT)
            ELSE NULL 
        END AS player_age_at_match
    FROM temp_part_v3b p
    JOIN dim_match m ON p.match_id = m.match_id
    JOIN dim_match_context c ON m.match_id = c.match_id
    LEFT JOIN temp_venue_mapping vm ON c.venue_name = vm.raw_venue_name
    LEFT JOIN temp_master_enriched pme ON p.player_id = pme.player_id
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

    cols = [field.name for field in PLAYER_MATCH_SCHEMA_V3B]
    select_cols = ", ".join(cols)
    df = con.execute(f"SELECT {select_cols} FROM temp_player_match").df()
    logger.info("Extracted %d player-match records across %d fields.", len(df), len(cols))
    return df


def generate_and_materialize_baselines(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
) -> Dict[str, int]:
    """Generate empirical ground, phase, and opposition baselines."""
    ensure_canonical_venues_loaded(con)
    baselines_dir = output_dir / "contextual_baselines"
    if baselines_dir.exists():
        shutil.rmtree(baselines_dir)
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

    return baseline_counts


def write_feature_metadata(output_dir: Path) -> None:
    """Write catalog and lineage metadata to feature_metadata directory."""
    meta_dir = output_dir / "feature_metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    catalog = {
        "version": FEATURE_STORE_VERSION_V3B,
        "description": "CricEngine AI Phase 3B Enriched Point-in-Time Feature Store",
        "datasets": {
            "player_match": {
                "description": "Atomic match-level player box scores enriched with attributes and corrected starting XI",
                "columns": [f.name for f in PLAYER_MATCH_SCHEMA_V3B],
                "enrichments_v3b": [
                    "batting_hand",
                    "bowling_style",
                    "pace_spin_class",
                    "primary_role",
                    "player_age_at_match",
                ],
            },
            "rolling_match": {
                "description": "Match-based moving window performance features",
                "windows": MATCH_WINDOWS,
                "columns": [f.name for f in ROLLING_MATCH_SCHEMA],
            },
            "rolling_time": {
                "description": "Calendar-time moving window features with half-life decay",
                "windows_days": TIME_WINDOWS_DAYS,
                "columns": [f.name for f in ROLLING_TIME_SCHEMA],
            },
            "contextual_features": {
                "description": "Expanding contextual adjustments and park factors",
                "columns": [f.name for f in CONTEXTUAL_FEATURES_SCHEMA],
            },
        },
    }
    with open(meta_dir / "feature_catalog_v1.json", "w") as f:
        json.dump(catalog, f, indent=2)

    lineage = {
        "pipeline": "build_feature_store_v3b.py",
        "version": FEATURE_STORE_VERSION_V3B,
        "sources": [
            "data/datalake/curated/cricengine.duckdb",
            "data/datalake/enrichment_v3b/fact_match_participation_v3b.parquet",
            "data/datalake/enrichment_v3b/dim_player_master_enriched.parquet",
        ],
    }
    with open(meta_dir / "transformation_lineage.json", "w") as f:
        json.dump(lineage, f, indent=2)


def write_feature_store_manifest(
    output_dir: Path,
    db_sha256: str,
    db_size: int,
    metrics: Dict[str, Any],
) -> None:
    """Generate global manifest for Phase 3B feature store."""
    manifest = {
        "feature_store_version": FEATURE_STORE_VERSION_V3B,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_database": {
            "path": "data/datalake/curated/cricengine.duckdb",
            "sha256": db_sha256,
            "size_bytes": db_size,
        },
        "compression": "SNAPPY",
        "formats_supported": FORMATS,
        "match_windows": MATCH_WINDOWS,
        "time_windows_days": TIME_WINDOWS_DAYS,
        "datasets": metrics,
    }
    manifest_file = output_dir / "_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Wrote global manifest to %s", manifest_file)


def build_feature_store_v3b(
    db_path: Path = Path("data/datalake/curated/cricengine.duckdb"),
    output_dir: Path = Path("data/datalake/feature_store_v3b"),
    part_v3b_parquet: Path = Path("data/datalake/enrichment_v3b/fact_match_participation_v3b.parquet"),
    enriched_master_parquet: Path = Path("data/datalake/enrichment_v3b/dim_player_master_enriched.parquet"),
) -> Dict[str, Any]:
    """Execute complete Phase 3B Feature Store materialization."""
    start_time = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Pre-run Curated DuckDB Verification...")
    init_sha256 = calculate_file_sha256(db_path)
    init_size = db_path.stat().st_size
    logger.info("DuckDB SHA-256: %s, Size: %d", init_sha256, init_size)

    con = duckdb.connect(str(db_path), read_only=True)
    dataset_metrics = {}

    try:
        # 1. Player Match Dataset
        logger.info("\n--- Phase 1: Materializing player_match (v3b Enriched) ---")
        t0 = time.time()
        df_pm = extract_player_match_dataframe_v3b(con, part_v3b_parquet, enriched_master_parquet)
        pm_path = output_dir / "player_match"
        if pm_path.exists():
            shutil.rmtree(pm_path)
        write_partitioned_dataset(
            df_pm,
            PLAYER_MATCH_SCHEMA_V3B,
            partition_cols=["match_format", "season"],
            output_path=pm_path,
        )
        dataset_metrics["player_match"] = {
            "row_count": len(df_pm),
            "columns": len(PLAYER_MATCH_SCHEMA_V3B),
            "duration_seconds": round(time.time() - t0, 2),
            "partitions": ["match_format", "season"],
        }

        # 2. Rolling Match Dataset (L5, L10, L20)
        logger.info("\n--- Phase 2: Materializing rolling_match (L5, L10, L20) ---")
        rm_path = output_dir / "rolling_match"
        if rm_path.exists():
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

        # 3. Rolling Time Dataset (30d, 90d, 365d)
        logger.info("\n--- Phase 3: Materializing rolling_time (30d, 90d, 365d) ---")
        rt_path = output_dir / "rolling_time"
        if rt_path.exists():
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

        # 4. Contextual Features
        logger.info("\n--- Phase 4: Materializing Contextual Features ---")
        t0 = time.time()
        df_ctx = extract_contextual_features_dataframe(con)
        ctx_path = output_dir / "contextual_features"
        if ctx_path.exists():
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

        # 5. Contextual Baselines
        logger.info("\n--- Phase 5: Generating Contextual Baselines ---")
        baselines = generate_and_materialize_baselines(con, output_dir)
        dataset_metrics["contextual_baselines"] = baselines

        # 6. Metadata and Manifest
        logger.info("\n--- Phase 6: Emitting Metadata and Manifest ---")
        write_feature_metadata(output_dir)
        write_feature_store_manifest(output_dir, init_sha256, init_size, dataset_metrics)

    finally:
        con.close()
        logger.info("Closed read-only DuckDB connection.")

    # Post-run Database Immutability Check
    post_sha256 = calculate_file_sha256(db_path)
    post_size = db_path.stat().st_size
    assert init_sha256 == post_sha256, f"FATAL: DuckDB checksum changed! {init_sha256} != {post_sha256}"
    assert init_size == post_size, f"FATAL: DuckDB size changed! {init_size} != {post_size}"
    logger.info("DATABASE IMMUTABILITY VERIFIED: Checksum and byte size are identical.")

    logger.info("Pipeline completed successfully in %.2f seconds.", time.time() - start_time)
    return dataset_metrics


def generate_checksums(feature_store_dir: Path, output_file: Path) -> None:
    """Generate SHA-256 checksums for all files in feature_store_v3b."""
    logger.info("Computing SHA-256 checksums for %s...", feature_store_dir)
    checksums = {}
    for p in sorted(feature_store_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(feature_store_dir))
            checksums[rel] = {
                "sha256": calculate_file_sha256(p),
                "size_bytes": p.stat().st_size,
            }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(
            {
                "version": FEATURE_STORE_VERSION_V3B,
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "file_count": len(checksums),
                "checksums": checksums,
            },
            f,
            indent=2,
        )
    logger.info("Wrote %d file checksums to %s", len(checksums), output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Phase 3B Feature Store")
    parser.add_argument("--db-path", type=Path, default=Path("data/datalake/curated/cricengine.duckdb"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/datalake/feature_store_v3b"))
    args = parser.parse_args()

    build_feature_store_v3b(args.db_path, args.output_dir)
    generate_checksums(args.output_dir, Path("docs/feature_store_v3b_checksums.json"))
