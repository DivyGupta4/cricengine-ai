-- ==============================================================================
-- CricEngine AI — Verified Professor Demonstration SQL Queries
-- Canonical Database: data/datalake/curated/cricengine.duckdb
-- Parquet Stores:     data/datalake/feature_store_v3b/
--                     data/datalake/rating_store_v4/
--                     data/datalake/predictive_store_v4c/
--
-- All queries tested and verified against actual schemas and data.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- QUERY 1: Match-Level Data (Dimension & Context)
-- Demonstrates: Relational join of dim_match and dim_match_context.
-- Highlights: Standardized metadata, tournament stage, venue, and outcome margin.
-- Example: India vs Australia T20I (Match ID: 1389392)
-- ------------------------------------------------------------------------------
SELECT 
    m.match_id,
    m.competition_name,
    m.match_format,
    m.season,
    m.start_date,
    m.team_1,
    m.team_2,
    c.venue_name,
    c.city,
    c.toss_winner,
    c.toss_decision,
    c.outcome_winner,
    c.win_by_type,
    c.win_by_margin
FROM dim_match m
JOIN dim_match_context c ON m.match_id = c.match_id
WHERE m.match_id = '1389392';


-- ------------------------------------------------------------------------------
-- QUERY 2: Delivery-Level Data (Ball-by-Ball Fact Table)
-- Demonstrates: Granular event-level data with batter, bowler, runs, extras & wickets.
-- Highlights: First over (over_num = 0) of 1st Innings in Match 1389392.
-- ------------------------------------------------------------------------------
SELECT 
    b.innings_num,
    b.over_num,
    b.delivery_num,
    bat.canonical_name AS batter_name,
    bowl.canonical_name AS bowler_name,
    b.runs_batter,
    b.runs_extras,
    b.runs_total,
    b.wides,
    b.noballs,
    b.is_wicket,
    b.match_phase
FROM fact_ball_by_ball b
JOIN dim_player_master bat ON b.batter_id = bat.player_id
JOIN dim_player_master bowl ON b.bowler_id = bowl.player_id
WHERE b.match_id = '1389392' 
  AND b.innings_num = 1 
  AND b.over_num = 0
ORDER BY b.delivery_num;


-- ------------------------------------------------------------------------------
-- QUERY 3: Player Participation and Role Verification
-- Demonstrates: Match roster participation, Starting XI status, and activity flags.
-- Highlights: Verified participation facts resolved with dim_player_master.
-- ------------------------------------------------------------------------------
SELECT 
    p.team_name,
    pm.canonical_name AS player_name,
    p.participation_role,
    p.in_starting_xi,
    p.batted_flag,
    p.bowled_flag,
    p.fielded_flag,
    p.evidence_confidence
FROM fact_match_participation p
JOIN dim_player_master pm ON p.player_id = pm.player_id
WHERE p.match_id = '1389392'
ORDER BY p.team_name, pm.canonical_name;


-- ------------------------------------------------------------------------------
-- QUERY 4: Dismissal Events with Bowler and Fielder Attribution
-- Demonstrates: Complex relational join connecting dismissals, ball events,
--               credited bowlers, and assisted fielders (catches, stumpings, run-outs).
-- ------------------------------------------------------------------------------
SELECT 
    d.innings_num,
    d.dismissal_seq,
    out_p.canonical_name AS batter_dismissed,
    d.dismissal_kind,
    bowl_p.canonical_name AS credited_bowler,
    COALESCE(f_p.canonical_name, 'None (Unassisted / Bowled / LBW)') AS credited_fielder,
    f.is_substitute AS fielder_is_substitute
FROM fact_delivery_dismissal d
JOIN dim_player_master out_p ON d.player_out_id = out_p.player_id
JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
JOIN dim_player_master bowl_p ON b.bowler_id = bowl_p.player_id
LEFT JOIN fact_dismissal_fielder f ON d.dismissal_id = f.dismissal_id
LEFT JOIN dim_player_master f_p ON f.fielder_id = f_p.player_id
WHERE d.match_id = '1389392'
ORDER BY d.innings_num, d.dismissal_seq;


-- ------------------------------------------------------------------------------
-- QUERY 5: Feature Store — Single Match Performance Metrics (Parquet Lakehouse)
-- Demonstrates: Querying transformed Parquet feature partitions directly via DuckDB.
-- Highlights: 49 engineered metrics per player-match including loads, strike rates,
--             and fielding contributions.
-- ------------------------------------------------------------------------------
SELECT 
    pm.canonical_name,
    f.team_name,
    f.batting_position,
    f.runs_scored,
    f.balls_faced,
    f.boundary_fours,
    f.boundary_sixes,
    ROUND(f.strike_rate, 1) AS strike_rate,
    f.overs_bowled,
    f.runs_conceded,
    f.wickets_credited,
    ROUND(f.economy_rate, 2) AS economy_rate,
    f.catches_taken,
    f.primary_role
FROM read_parquet('data/datalake/feature_store_v3b/player_match/**/*.parquet', hive_partitioning=true) f
JOIN dim_player_master pm ON f.player_id = pm.player_id
WHERE f.match_id = '1389392'
ORDER BY f.runs_scored DESC;


-- ------------------------------------------------------------------------------
-- QUERY 6: Historical Rolling Features — Multi-Window Form & Recency
-- Demonstrates: Rolling moving windows (5, 10, 20 matches) with exponential decay
--               and shrinkage to prevent sample-size noise and lookahead leakage.
-- ------------------------------------------------------------------------------
SELECT 
    pm.canonical_name,
    rm.window_size,
    rm.matches_in_window,
    rm.rolling_runs_scored,
    ROUND(rm.rolling_batting_avg, 2) AS rolling_batting_avg,
    ROUND(rm.rolling_batting_sr, 2) AS rolling_batting_sr,
    rm.rolling_wickets_taken,
    ROUND(rm.rolling_economy_rate, 2) AS rolling_economy_rate,
    ROUND(rm.decayed_batting_sr, 2) AS decayed_batting_sr,
    rm.days_since_last_match
FROM read_parquet('data/datalake/feature_store_v3b/rolling_match/**/*.parquet', hive_partitioning=true) rm
JOIN dim_player_master pm ON rm.player_id = pm.player_id
WHERE rm.match_id = '1389392' 
  AND pm.canonical_name IN ('SA Yadav', 'GJ Maxwell', 'Ravi Bishnoi', 'RD Gaikwad')
ORDER BY pm.canonical_name, rm.window_size;


-- ------------------------------------------------------------------------------
-- QUERY 7: Rating Store — Pre-Match Latent Skill Snapshots (D-1 Zero-Leakage)
-- Demonstrates: Bayesian latent skill parameters (theta, rating r, deviation rd)
--               evaluated strictly prior to the toss.
-- ------------------------------------------------------------------------------
SELECT 
    pm.canonical_name,
    s.inferred_role,
    ROUND(s.pre_r_bat, 1) AS pre_rating_bat,
    ROUND(s.pre_rd_bat, 1) AS uncertainty_bat,
    ROUND(s.pre_r_bowl, 1) AS pre_rating_bowl,
    ROUND(s.pre_rd_bowl, 1) AS uncertainty_bowl,
    ROUND(s.pre_vorp, 2) AS baseline_expected_vorp
FROM read_parquet('data/datalake/rating_store_v4/pre_match_snapshots/**/*.parquet', hive_partitioning=true) s
JOIN dim_player_master pm ON s.player_id = pm.player_id
WHERE s.match_id = '1389392'
ORDER BY s.pre_vorp DESC
LIMIT 10;


-- ------------------------------------------------------------------------------
-- QUERY 8: Predictive Store — Value Over Replacement Player (VORP)
-- Demonstrates: Evaluating actual match impact against role-calibrated replacement baselines.
-- ------------------------------------------------------------------------------
SELECT 
    pm.canonical_name,
    v.inferred_role,
    v.match_format,
    ROUND(v.vorp_bat, 2) AS vorp_batting,
    ROUND(v.vorp_bowl, 2) AS vorp_bowling,
    ROUND(v.vorp_field, 2) AS vorp_fielding,
    ROUND(v.vorp_total, 2) AS vorp_total,
    v.is_above_replacement
FROM read_parquet('data/datalake/predictive_store_v4c/player_match_vorp/**/*.parquet', hive_partitioning=true) v
JOIN dim_player_master pm ON v.player_id = pm.player_id
WHERE v.match_id = '1389392'
ORDER BY v.vorp_total DESC
LIMIT 10;


-- ------------------------------------------------------------------------------
-- QUERY 9: Unified End-to-End Lineage Join (Database + Feature + Rating + Predictive)
-- Demonstrates: Complete enterprise data lineage in a single analytical SQL query:
--               Relational Master -> Feature Store -> Rating Store -> VORP Store.
-- ------------------------------------------------------------------------------
SELECT 
    pm.canonical_name,
    p.team_name,
    s.inferred_role,
    f.runs_scored,
    f.balls_faced,
    f.wickets_credited,
    ROUND(s.pre_r_bat, 1) AS pre_match_rating_bat,
    ROUND(s.pre_r_bowl, 1) AS pre_match_rating_bowl,
    ROUND(v.vorp_total, 2) AS match_vorp_generated
FROM fact_match_participation p
JOIN dim_player_master pm ON p.player_id = pm.player_id
JOIN read_parquet('data/datalake/feature_store_v3b/player_match/**/*.parquet', hive_partitioning=true) f 
    ON p.match_id = f.match_id AND p.player_id = f.player_id
JOIN read_parquet('data/datalake/rating_store_v4/pre_match_snapshots/**/*.parquet', hive_partitioning=true) s 
    ON p.match_id = s.match_id AND p.player_id = s.player_id
JOIN read_parquet('data/datalake/predictive_store_v4c/player_match_vorp/**/*.parquet', hive_partitioning=true) v 
    ON p.match_id = v.match_id AND p.player_id = v.player_id
WHERE p.match_id = '1389392'
ORDER BY v.vorp_total DESC;
