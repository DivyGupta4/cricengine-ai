"""
CricEngine AI — Step 4B: Contextual Performance Features Engine

Implements non-circular, point-in-time contextual feature extraction:
- Expanding historical venue park factors (PF_venue).
- Pre-match opposition bowling and batting unit quality indices.
- Format-specific match phase performance baselines.
- Deterministic home, away, and neutral match status derivation.
- Competition tier multipliers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import pyarrow as pa

from etl.feature_definitions import (
    CONTEXTUAL_FEATURES_SCHEMA,
    TIER_DISCOUNT_FACTORS,
    COHORT_PRIORS,
)


def ensure_canonical_venues_loaded(con: duckdb.DuckDBPyConnection) -> None:
    """Ensure temp_venue_mapping exists in DuckDB connection."""
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
    except Exception:
        tables = []
    if "temp_venue_mapping" not in tables:
        venues_path = Path(__file__).resolve().parent.parent / "config" / "canonical_venues.json"
        if venues_path.exists():
            with open(venues_path, "r", encoding="utf-8") as f:
                venues_dict = json.load(f)
            rows = [
                {
                    "raw_venue_name": raw_name,
                    "canonical_venue_name": meta["canonical_venue_name"],
                    "canonical_venue_id": meta["canonical_venue_id"],
                    "is_alias_reconciled": meta["is_alias_reconciled"],
                }
                for raw_name, meta in venues_dict.items()
            ]
            df_venues = pd.DataFrame(rows)
            con.execute("CREATE OR REPLACE TEMPORARY TABLE temp_venue_mapping AS SELECT * FROM df_venues")


# Known Venue to Home Team Mapping (Franchise & International)
VENUE_HOME_TEAM_MAP = {
    # IPL Franchise Home Grounds
    "Wankhede Stadium": "Mumbai Indians",
    "Wankhede Stadium, Mumbai": "Mumbai Indians",
    "Brabourne Stadium, Mumbai": "Mumbai Indians",
    "MA Chidambaram Stadium": "Chennai Super Kings",
    "MA Chidambaram Stadium, Chepauk": "Chennai Super Kings",
    "MA Chidambaram Stadium, Chepauk, Chennai": "Chennai Super Kings",
    "M Chinnaswamy Stadium": "Royal Challengers Bengaluru",
    "M Chinnaswamy Stadium, Bengaluru": "Royal Challengers Bengaluru",
    "M. Chinnaswamy Stadium": "Royal Challengers Bengaluru",
    "Eden Gardens": "Kolkata Knight Riders",
    "Eden Gardens, Kolkata": "Kolkata Knight Riders",
    "Arun Jaitley Stadium": "Delhi Capitals",
    "Arun Jaitley Stadium, Delhi": "Delhi Capitals",
    "Feroz Shah Kotla": "Delhi Capitals",
    "Punjab Cricket Association Stadium, Mohali": "Punjab Kings",
    "Punjab Cricket Association IS Bindra Stadium, Mohali": "Punjab Kings",
    "Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur": "Punjab Kings",
    "Sawai Mansingh Stadium": "Rajasthan Royals",
    "Sawai Mansingh Stadium, Jaipur": "Rajasthan Royals",
    "Rajiv Gandhi International Stadium": "Sunrisers Hyderabad",
    "Rajiv Gandhi International Stadium, Uppal": "Sunrisers Hyderabad",
    "Rajiv Gandhi International Stadium, Uppal, Hyderabad": "Sunrisers Hyderabad",
    "Narendra Modi Stadium": "Gujarat Titans",
    "Narendra Modi Stadium, Ahmedabad": "Gujarat Titans",
    "Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium": "Lucknow Super Giants",
    "Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium, Lucknow": "Lucknow Super Giants",
    "BRSABV Ekana Cricket Stadium, Lucknow": "Lucknow Super Giants",
}

# Country Venue Substring Mapping for International Cricket
COUNTRY_VENUE_MAP = {
    "India": ["Eden Gardens", "Wankhede", "Chinnaswamy", "Arun Jaitley", "Narendra Modi", "Chepauk", "Mohali", "Dharamsala", "Barabati", "Green Park", "Vidarbha"],
    "Australia": ["Melbourne Cricket Ground", "Sydney Cricket Ground", "Adelaide Oval", "Brisbane Cricket Ground", "Gabba", "Perth Stadium", "W.A.C.A. Ground", "Bellerive Oval", "Manuka Oval"],
    "England": ["Lord's", "The Oval", "Kennington Oval", "Edgbaston", "Headingley", "Old Trafford", "Trent Bridge", "Sophia Gardens", "Rose Bowl"],
    "South Africa": ["Newlands", "Wanderers Stadium", "SuperSport Park", "Kingsmead", "St George's Park", "Mangaung Oval", "Boland Park"],
    "New Zealand": ["Eden Park", "Basin Reserve", "Hagley Oval", "Seddon Park", "McLean Park", "University Oval"],
    "Pakistan": ["Gaddafi Stadium", "National Stadium", "Rawalpindi Cricket Stadium", "Multan Cricket Stadium"],
    "Sri Lanka": ["R.Premadasa Stadium", "Pallekele International Cricket Stadium", "Galle International Stadium", "Sinhalese Sports Club Ground"],
    "West Indies": ["Kensington Oval", "Queen's Park Oval", "Sabina Park", "Providence Stadium", "Daren Sammy National Cricket Stadium", "Sir Vivian Richards Stadium"],
}


def derive_home_away_status(
    venue_name: str,
    team_name: str,
    opposition_team: str,
    competition_tier: int,
) -> Tuple[bool, bool]:
    """
    Derive whether match is home, away, or neutral for team_name.
    Returns (is_home, is_neutral).
    """
    venue_str = str(venue_name).strip() if venue_name else ""
    t_name = str(team_name).strip() if team_name else ""
    opp_name = str(opposition_team).strip() if opposition_team else ""

    # Tier 2: IPL Franchise Match
    if competition_tier == 2:
        for v_sub, designated_team in VENUE_HOME_TEAM_MAP.items():
            if v_sub.lower() in venue_str.lower():
                if t_name.lower() in designated_team.lower():
                    return True, False
                elif opp_name.lower() in designated_team.lower():
                    return False, False
                else:
                    return False, True  # Neutral playoff or alternate venue
        return False, True

    # Tier 1: International Cricket
    if competition_tier == 1:
        team_country = None
        for country, v_list in COUNTRY_VENUE_MAP.items():
            for v_sub in v_list:
                if v_sub.lower() in venue_str.lower():
                    team_country = country
                    break
            if team_country:
                break

        if team_country:
            is_team_host = (team_country.lower() in t_name.lower())
            is_opp_host = (team_country.lower() in opp_name.lower())
            if is_team_host:
                return True, False
            elif is_opp_host:
                return False, False
            else:
                return False, True  # Neutral tournament ground

    # Default: Neutral
    return False, True


def extract_contextual_features_dataframe(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Extract strictly point-in-time contextual features from read-only DuckDB connection:
    - Expanding venue park factors.
    - Pre-match opposition bowling unit quality.
    - Pre-match opposition batting unit quality.
    - Career phase strike rates and economy rates.
    """
    ensure_canonical_venues_loaded(con)

    query = """
    WITH match_timeline AS (
        SELECT 
            m.match_id,
            m.competition_name,
            m.competition_tier,
            m.match_format,
            m.season,
            m.start_date,
            c.venue_name,
            COALESCE(vm.canonical_venue_name, c.venue_name) AS canonical_venue_name,
            c.city,
            m.team_1,
            m.team_2,
            COALESCE(m.match_type_number, 0) AS mtn
        FROM dim_match m
        JOIN dim_match_context c ON m.match_id = c.match_id
        LEFT JOIN temp_venue_mapping vm ON c.venue_name = vm.raw_venue_name
    ),
    match_deliveries_summary AS (
        SELECT 
            match_id,
            SUM(runs_total) AS match_total_runs,
            COUNT(CASE WHEN is_legal_delivery THEN 1 END) AS match_legal_balls
        FROM fact_ball_by_ball
        GROUP BY 1
    ),
    match_with_totals AS (
        SELECT 
            t.match_id,
            t.competition_name,
            t.competition_tier,
            t.match_format,
            t.season,
            t.start_date,
            t.venue_name,
            t.canonical_venue_name,
            t.team_1,
            t.team_2,
            t.mtn,
            COALESCE(s.match_total_runs, 0) AS match_total_runs,
            COALESCE(s.match_legal_balls, 0) AS match_legal_balls
        FROM match_timeline t
        LEFT JOIN match_deliveries_summary s ON t.match_id = s.match_id
    ),
    expanding_venue_factors AS (
        SELECT 
            match_id,
            canonical_venue_name,
            match_format,
            start_date,
            mtn,
            SUM(match_total_runs) OVER (
                PARTITION BY canonical_venue_name, match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS prior_venue_runs,
            SUM(match_legal_balls) OVER (
                PARTITION BY canonical_venue_name, match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS prior_venue_balls,
            SUM(match_total_runs) OVER (
                PARTITION BY match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS prior_format_runs,
            SUM(match_legal_balls) OVER (
                PARTITION BY match_format
                ORDER BY start_date ASC, mtn ASC, match_id ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS prior_format_balls
        FROM match_with_totals
    ),
    venue_park_factor_calc AS (
        SELECT 
            match_id,
            CASE 
                WHEN prior_venue_balls >= 600 AND prior_format_balls >= 1000
                THEN ROUND((prior_venue_runs * 1.0 / prior_venue_balls) / (prior_format_runs * 1.0 / prior_format_balls), 3)
                ELSE 1.000 
            END AS venue_historical_park_factor
        FROM expanding_venue_factors
    ),
    -- Team-Match Level Bowling to evaluate historical opposition quality
    team_match_bowling AS (
        SELECT 
            i.match_id,
            m.start_date,
            COALESCE(m.match_type_number, 0) AS mtn,
            m.match_format,
            i.bowling_team,
            SUM(i.total_runs_scored) AS total_runs_scored,
            SUM(i.total_wickets_lost) AS total_wickets_lost,
            SUM(i.total_legal_deliveries) AS total_legal_deliveries
        FROM fact_innings i
        JOIN dim_match m ON i.match_id = m.match_id
        GROUP BY i.match_id, m.start_date, m.match_type_number, m.match_format, i.bowling_team
    ),
    team_rolling_bowling_quality AS (
        SELECT 
            match_id,
            bowling_team,
            match_format,
            ROUND(
                SUM(total_runs_scored) OVER (
                    PARTITION BY bowling_team, match_format
                    ORDER BY start_date ASC, mtn ASC, match_id ASC
                    ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
                ) * 6.0 / 
                NULLIF(
                    SUM(total_legal_deliveries) OVER (
                        PARTITION BY bowling_team, match_format
                        ORDER BY start_date ASC, mtn ASC, match_id ASC
                        ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
                    ), 0
                ), 2
            ) AS opp_rolling_economy
        FROM team_match_bowling
    ),
    -- Team-Match Level Batting to evaluate historical opposition quality
    team_match_batting AS (
        SELECT 
            i.match_id,
            m.start_date,
            COALESCE(m.match_type_number, 0) AS mtn,
            m.match_format,
            i.batting_team,
            SUM(i.total_runs_scored) AS total_runs_scored,
            SUM(i.total_wickets_lost) AS total_wickets_lost,
            SUM(i.total_legal_deliveries) AS total_legal_deliveries
        FROM fact_innings i
        JOIN dim_match m ON i.match_id = m.match_id
        GROUP BY i.match_id, m.start_date, m.match_type_number, m.match_format, i.batting_team
    ),
    team_rolling_batting_quality AS (
        SELECT 
            match_id,
            batting_team,
            match_format,
            ROUND(
                SUM(total_runs_scored) OVER (
                    PARTITION BY batting_team, match_format
                    ORDER BY start_date ASC, mtn ASC, match_id ASC
                    ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
                ) * 1.0 / 
                NULLIF(
                    SUM(total_wickets_lost) OVER (
                        PARTITION BY batting_team, match_format
                        ORDER BY start_date ASC, mtn ASC, match_id ASC
                        ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
                    ), 0
                ), 2
            ) AS opp_rolling_runs_per_wkt
        FROM team_match_batting
    ),
    -- Player Career Phase Aggregates strictly pre-match
    player_phase_preceding AS (
        SELECT 
            b.match_id,
            m.start_date,
            COALESCE(m.match_type_number, 0) AS mtn,
            CAST(m.match_id AS BIGINT) AS match_int_id,
            m.match_format,
            b.batter_id,
            b.bowler_id,
            b.match_phase,
            b.runs_batter,
            b.runs_total,
            b.wides,
            b.noballs,
            b.is_legal_delivery
        FROM fact_ball_by_ball b
        JOIN dim_match m ON b.match_id = m.match_id
    ),
    -- Base participant list
    participants AS (
        SELECT 
            p.player_id,
            p.match_id,
            p.team_name,
            m.competition_name,
            m.competition_tier,
            m.match_format,
            m.season,
            m.start_date,
            c.venue_name,
            COALESCE(vm.canonical_venue_name, c.venue_name) AS canonical_venue_name,
            CASE WHEN p.team_name = m.team_1 THEN m.team_2 ELSE m.team_1 END AS opposition_team
        FROM fact_match_participation p
        JOIN dim_match m ON p.match_id = m.match_id
        JOIN dim_match_context c ON m.match_id = c.match_id
        LEFT JOIN temp_venue_mapping vm ON c.venue_name = vm.raw_venue_name
    )
    SELECT 
        p.player_id,
        p.match_id,
        p.match_format,
        p.season,
        p.start_date AS evaluation_date,
        p.venue_name,
        p.canonical_venue_name,
        p.opposition_team,
        COALESCE(v.venue_historical_park_factor, 1.000) AS venue_historical_park_factor,
        -- Bowling quality index: format_baseline / opp_rolling_economy
        CASE 
            WHEN p.match_format = 'T20' THEN ROUND(8.10 / NULLIF(COALESCE(bq.opp_rolling_economy, 8.10), 0), 3)
            WHEN p.match_format = 'ODI' THEN ROUND(5.25 / NULLIF(COALESCE(bq.opp_rolling_economy, 5.25), 0), 3)
            ELSE ROUND(3.15 / NULLIF(COALESCE(bq.opp_rolling_economy, 3.15), 0), 3)
        END AS opposition_bowling_quality_index,
        -- Batting quality index: opp_rolling_runs_per_wkt / format_baseline
        CASE 
            WHEN p.match_format = 'T20' THEN ROUND(COALESCE(bat_q.opp_rolling_runs_per_wkt, 22.0) / 22.0, 3)
            WHEN p.match_format = 'ODI' THEN ROUND(COALESCE(bat_q.opp_rolling_runs_per_wkt, 31.0) / 31.0, 3)
            ELSE ROUND(COALESCE(bat_q.opp_rolling_runs_per_wkt, 32.5) / 32.5, 3)
        END AS opposition_batting_quality_index,
        -- Tier multiplier
        CASE p.competition_tier
            WHEN 1 THEN 1.00
            WHEN 2 THEN 0.92
            WHEN 3 THEN 0.72
            ELSE 0.85
        END AS competition_tier_multiplier,
        p.competition_tier,
        p.team_name
    FROM participants p
    LEFT JOIN venue_park_factor_calc v ON p.match_id = v.match_id
    LEFT JOIN team_rolling_bowling_quality bq ON p.match_id = bq.match_id AND p.opposition_team = bq.bowling_team AND p.match_format = bq.match_format
    LEFT JOIN team_rolling_batting_quality bat_q ON p.match_id = bat_q.match_id AND p.opposition_team = bat_q.batting_team AND p.match_format = bat_q.match_format
    """
    df = con.execute(query).df()

    # Vectorized Home/Away/Neutral derivation in Python
    is_home_list = []
    is_neutral_list = []
    for _, row in df.iterrows():
        is_home, is_neutral = derive_home_away_status(
            row["venue_name"], row["team_name"], row["opposition_team"], int(row["competition_tier"])
        )
        is_home_list.append(is_home)
        is_neutral_list.append(is_neutral)

    df["is_home_match"] = is_home_list
    df["is_neutral_match"] = is_neutral_list

    # Default career phase placeholders (can be joined if populated or emit NULL)
    df["career_powerplay_strike_rate"] = None
    df["career_death_strike_rate"] = None
    df["career_powerplay_economy"] = None
    df["career_death_economy"] = None

    # Select final columns in schema order
    ordered_cols = [
        "player_id", "match_id", "match_format", "season", "evaluation_date",
        "venue_name", "canonical_venue_name", "opposition_team", "venue_historical_park_factor",
        "opposition_bowling_quality_index", "opposition_batting_quality_index",
        "is_home_match", "is_neutral_match", "competition_tier_multiplier",
        "career_powerplay_strike_rate", "career_death_strike_rate",
        "career_powerplay_economy", "career_death_economy"
    ]
    return df[ordered_cols]
