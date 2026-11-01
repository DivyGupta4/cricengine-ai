"""
CricEngine AI — Chronological Rating Execution Engine (Phase 4B)
Context-Adjusted Hierarchical Bayesian State-Space (CA-HBSS)
"""

from __future__ import annotations
import math
import os
import resource
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import duckdb
import numpy as np
import pandas as pd

from src.ratings.config import (
    BASE_DIR,
    CURATED_DB_PATH,
    FEATURE_STORE_V3B_DIR,
    RATING_STORE_V4_DIR,
    FORMATS,
    FORMAT_CONFIGS,
    DEFAULT_CONFIG,
    FormatConfig,
    RatingEngineConfig,
)
from src.ratings.state_model import PlayerRatingState
from src.ratings.batting import update_batting_state
from src.ratings.bowling import update_bowling_state
from src.ratings.fielding import update_fielding_state
from src.ratings.all_round import compute_all_round_and_vorp
from src.ratings.contextual_adjustments import ContextualEngine
from src.ratings.temporal_dynamics import apply_temporal_drift
from src.ratings.role_inference import infer_dynamic_role
from src.ratings.identity_resolution import IdentityManager
from src.ratings.rating_store import RatingStore


def ensure_file_descriptor_limit():
    """Increases open file descriptor limit to avoid macOS/Linux limits when reading partitioned Parquet."""
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < 4096:
            target = min(4096, hard) if hard > 0 else 4096
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except Exception:
        pass


class ChronologicalRatingEngine:
    """
    Executes leak-free chronological player rating updates across all matches.
    Enforces Daily Batch Evaluation Boundaries to prevent same-day match leakage.
    """

    def __init__(
        self,
        config: Optional[RatingEngineConfig] = None,
        feature_store_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        self.config = config or DEFAULT_CONFIG
        self.feature_store_dir = feature_store_dir or FEATURE_STORE_V3B_DIR
        self.output_dir = output_dir or RATING_STORE_V4_DIR
        
        ensure_file_descriptor_limit()
        
        # Initialize Subsystems
        venue_pf_path = self.feature_store_dir / "contextual_baselines" / "venue_park_factors.parquet"
        self.context_engine = ContextualEngine(venue_pf_path)
        self.identity_mgr = IdentityManager()
        self.store = RatingStore(self.output_dir)

        # Active state cache: { (player_id, match_format): PlayerRatingState }
        self.state_cache: Dict[Tuple[str, str], PlayerRatingState] = {}
        
        # Rolling player history for dynamic role inference: { (player_id, match_format): deque / list of stats }
        self.player_role_history: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

        # Audit counters
        self.audit = {
            "total_matches_processed": 0,
            "total_participations_evaluated": 0,
            "batting_observations_updated": 0,
            "bowling_observations_updated": 0,
            "fielding_observations_updated": 0,
            "zero_exposure_skips": 0,
            "numerical_failures": 0,
            "identity_uncertain_evaluations": 0,
            "start_time_utc": None,
            "end_time_utc": None,
            "elapsed_seconds": 0.0,
        }

    def load_dataset(self) -> pd.DataFrame:
        """
        Loads all player-match records and contextual covariates into memory
        sorted chronologically by (start_date ASC, match_id ASC).
        """
        pm_glob = str(self.feature_store_dir / "player_match" / "**" / "*.parquet")
        cf_glob = str(self.feature_store_dir / "contextual_features" / "**" / "*.parquet")
        
        conn = duckdb.connect()
        query = f"""
        SELECT 
            pm.match_id,
            pm.start_date,
            UPPER(pm.match_format) AS match_format,
            pm.player_id,
            COALESCE(pm.runs_scored, 0) AS runs_scored,
            COALESCE(pm.balls_faced, 0) AS balls_faced,
            COALESCE(pm.is_dismissed, FALSE) AS is_dismissed,
            COALESCE(pm.legal_balls_bowled, 0) AS legal_balls_bowled,
            COALESCE(pm.runs_conceded, 0) AS runs_conceded,
            COALESCE(pm.wickets_credited, 0) AS wickets_credited,
            COALESCE(pm.catches_taken, 0) AS catches_taken,
            COALESCE(pm.runouts_involved, 0) AS runouts_involved,
            COALESCE(pm.in_starting_xi, TRUE) AS in_starting_xi,
            COALESCE(pm.batting_load, 0.0) AS batting_load,
            COALESCE(pm.bowling_load, 0.0) AS bowling_load,
            pm.batting_position,
            pm.overs_bowled,
            pm.stumpings_taken,
            pm.pace_spin_class,
            COALESCE(cf.canonical_venue_name, pm.canonical_venue_name, pm.venue_name) AS canonical_venue_name,
            COALESCE(cf.venue_historical_park_factor, 1.000) AS venue_historical_park_factor,
            COALESCE(cf.opposition_bowling_quality_index, 1.000) AS opposition_bowling_quality_index,
            COALESCE(cf.opposition_batting_quality_index, 1.000) AS opposition_batting_quality_index
        FROM read_parquet('{pm_glob}', hive_partitioning=1) pm
        LEFT JOIN read_parquet('{cf_glob}', hive_partitioning=1) cf
            ON pm.match_id = cf.match_id AND pm.player_id = cf.player_id
        WHERE UPPER(pm.match_format) IN ('T20', 'ODI', 'TEST')
        ORDER BY pm.start_date ASC, pm.match_id ASC
        """
        df = conn.execute(query).df()
        conn.close()
        return df

    def get_or_create_state(self, player_id: str, match_format: str, as_of_date: str) -> PlayerRatingState:
        """Retrieves active state or creates a debutant prior."""
        key = (player_id, match_format)
        if key not in self.state_cache:
            status, _ = self.identity_mgr.get_identity_status_and_weight(player_id)
            self.state_cache[key] = PlayerRatingState.create_debutant(
                player_id=player_id,
                match_format=match_format,
                as_of_date=as_of_date,
                identity_status=status,
            )
        return self.state_cache[key]

    def run_pipeline(self) -> Dict[str, Any]:
        """
        Executes full chronological walk-forward rating updates across all formats.
        """
        start_time = time.time()
        self.audit["start_time_utc"] = datetime.now(timezone.utc).isoformat()
        
        print("[ChronologicalEngine] Loading feature store v3b dataset...")
        df = self.load_dataset()
        total_rows = len(df)
        print(f"[ChronologicalEngine] Loaded {total_rows:,} player-match records.")

        # Group chronologically by (start_date, match_format) daily batches
        # This guarantees that same-day matches do not contaminate each other
        grouped_batches = df.groupby(["start_date", "match_format"], sort=False)
        total_batches = len(grouped_batches)
        print(f"[ChronologicalEngine] Processing {total_batches:,} daily match batches...")

        history_records: List[Dict[str, Any]] = []
        pre_match_snapshots: List[Dict[str, Any]] = []
        distinct_matches_seen = set()

        batch_idx = 0
        for (batch_date, fmt), batch_df in grouped_batches:
            batch_idx += 1
            if batch_idx % 500 == 0 or batch_idx == total_batches:
                print(f"[ChronologicalEngine] Batch {batch_idx:,}/{total_batches:,} ({batch_date} - {fmt}) - Active States: {len(self.state_cache):,}")

            fmt_code = fmt.upper()
            if fmt_code not in FORMAT_CONFIGS:
                continue
            fmt_config = FORMAT_CONFIGS[fmt_code]
            date_str = str(batch_date)[:10]

            # 1. PRE-MATCH STAGE (Freeze prior states as of batch_date)
            # Query and apply temporal variance inflation for all participants in this day's batch
            pre_batch_states: Dict[str, PlayerRatingState] = {}
            for row in batch_df.itertuples(index=False):
                p_id = row.player_id
                distinct_matches_seen.add(row.match_id)
                
                # Fetch state
                curr_state = self.get_or_create_state(p_id, fmt_code, date_str)
                
                # Apply continuous-time variance inflation from last match
                curr_state = apply_temporal_drift(
                    state=curr_state,
                    current_match_date=date_str,
                    format_config=fmt_config,
                    rd_max=self.config.native_rd_max,
                )
                
                # Save pre-match snapshot (cloned)
                if p_id not in pre_batch_states:
                    pre_batch_states[p_id] = curr_state.copy()
                    
                    # Store pre-match sample snapshot for backtesting/validation
                    if batch_idx % 10 == 0:  # Sample every 10th batch to keep snapshot size manageable
                        pre_match_snapshots.append({
                            "player_id": p_id,
                            "match_id": row.match_id,
                            "match_date": date_str,
                            "match_format": fmt_code,
                            "pre_r_bat": round(curr_state.r_bat, 1),
                            "pre_rd_bat": round(curr_state.rd_bat, 1),
                            "pre_r_bowl": round(curr_state.r_bowl, 1),
                            "pre_rd_bowl": round(curr_state.rd_bowl, 1),
                            "pre_r_field": round(curr_state.r_field, 1),
                            "pre_rd_field": round(curr_state.rd_field, 1),
                            "pre_vorp": round(curr_state.vorp_rating, 2),
                            "inferred_role": curr_state.inferred_role,
                        })

            # 2. IN-MATCH OBSERVATION & UPDATE STAGE (Evaluate match outcomes)
            for row in batch_df.itertuples(index=False):
                p_id = row.player_id
                self.audit["total_participations_evaluated"] += 1
                
                state = self.state_cache[(p_id, fmt_code)]
                
                # Check identity status
                if state.identity_confidence_status != "VERIFIED":
                    self.audit["identity_uncertain_evaluations"] += 1

                # Dynamic Point-in-Time Role Inference (from pre-match history)
                hist = self.player_role_history[(p_id, fmt_code)]
                if len(hist) >= 5:
                    avg_pos = np.mean([h["pos"] for h in hist[-20:] if h["pos"] is not None] or [5.0])
                    avg_overs = np.mean([h["overs"] for h in hist[-20:]] or [0.0])
                    avg_stump = np.mean([h["stumpings"] for h in hist[-20:]] or [0.0])
                    role, conf, uflag = infer_dynamic_role(
                        rolling_batting_pos=avg_pos,
                        rolling_overs_bowled=avg_overs,
                        rolling_stumpings=avg_stump,
                        pace_spin_class=row.pace_spin_class,
                        matches_in_window=len(hist),
                    )
                    state.inferred_role = role
                    state.role_confidence = conf
                    state.role_uncertainty_flag = uflag

                # Contextual Factors
                shrunk_pf = self.context_engine.get_shrunk_park_factor(
                    canonical_venue=row.canonical_venue_name,
                    match_format=fmt_code,
                    raw_pf=row.venue_historical_park_factor,
                )
                obq = self.context_engine.sanitize_opp_bowling_quality(row.opposition_bowling_quality_index)
                bat_q = self.context_engine.sanitize_opp_batting_quality(row.opposition_batting_quality_index)

                # A. Batting Update
                if row.balls_faced > 0:
                    state = update_batting_state(
                        state=state,
                        runs_scored=int(row.runs_scored),
                        balls_faced=int(row.balls_faced),
                        is_dismissed=bool(row.is_dismissed),
                        park_factor=shrunk_pf,
                        opp_bowling_quality=obq,
                        format_config=fmt_config,
                        phi_runs=self.config.phi_bat_runs,
                    )
                    self.audit["batting_observations_updated"] += 1
                else:
                    self.audit["zero_exposure_skips"] += 1

                # B. Bowling Update
                if row.legal_balls_bowled > 0:
                    state = update_bowling_state(
                        state=state,
                        wickets_taken=int(row.wickets_credited),
                        runs_conceded=int(row.runs_conceded),
                        legal_balls_bowled=int(row.legal_balls_bowled),
                        park_factor=shrunk_pf,
                        opp_batting_quality=bat_q,
                        format_config=fmt_config,
                        phi_wkt=self.config.phi_bowl_wickets,
                        phi_econ=self.config.phi_bowl_econ,
                    )
                    self.audit["bowling_observations_updated"] += 1
                else:
                    self.audit["zero_exposure_skips"] += 1

                # C. Fielding Update (Exposure: 120 in T20, 300 in ODI, 450 in Test)
                team_field_exposure = 120 if fmt_code == "T20" else (300 if fmt_code == "ODI" else 450)
                if row.in_starting_xi:
                    state = update_fielding_state(
                        state=state,
                        catches_taken=int(row.catches_taken),
                        runouts_involved=int(row.runouts_involved),
                        in_starting_xi=bool(row.in_starting_xi),
                        team_balls_fielded=team_field_exposure,
                        format_config=fmt_config,
                        pi_zero=self.config.zip_zero_inflation,
                    )
                    self.audit["fielding_observations_updated"] += 1

                # D. All-Round & VORP Calculation (Additive, synergy = 0.0)
                compute_all_round_and_vorp(
                    state=state,
                    batting_load=float(row.batting_load),
                    bowling_load=float(row.bowling_load),
                    format_config=fmt_config,
                    replacement_level_rating=650.0,
                    roster_synergy_weight=self.config.roster_synergy_bonus_weight,
                )

                # Increment observation count and update dates
                state.observations_count += 1
                state.last_match_date = date_str
                state.as_of_date = date_str

                # Update player rolling history for role inference
                hist.append({
                    "pos": float(row.batting_position) if pd.notna(row.batting_position) else None,
                    "overs": float(row.overs_bowled) if pd.notna(row.overs_bowled) else 0.0,
                    "stumpings": float(row.stumpings_taken) if pd.notna(row.stumpings_taken) else 0.0,
                })

                # Checkpoint record (sample ~20% of match updates to keep history storage lean)
                if state.observations_count % 3 == 0 or state.observations_count == 1:
                    history_records.append(state.to_dict())

        # Final audit statistics
        elapsed = time.time() - start_time
        self.audit["total_matches_processed"] = len(distinct_matches_seen)
        self.audit["end_time_utc"] = datetime.now(timezone.utc).isoformat()
        self.audit["elapsed_seconds"] = round(elapsed, 2)
        print(f"[ChronologicalEngine] Pipeline run completed in {elapsed:.2f} seconds.")

        # 3. MATERIALIZATION STAGE
        print("[ChronologicalEngine] Materializing rating store v4...")
        states_by_format: Dict[str, List[PlayerRatingState]] = defaultdict(list)
        for (p_id, fmt), st in self.state_cache.items():
            states_by_format[fmt].append(st)

        current_counts = self.store.save_current_states(states_by_format)
        history_count = self.store.save_history_checkpoints(history_records)
        snapshot_count = self.store.save_pre_match_snapshots(pre_match_snapshots)

        manifest_path = self.store.write_metadata_and_manifest(
            config=self.config,
            input_provenance={
                "duckdb_curated_path": str(CURATED_DB_PATH),
                "feature_store_v3b_dir": str(self.feature_store_dir),
                "feature_store_version": "3.1.0-phase3b",
            },
            run_stats={
                "total_matches_processed": self.audit["total_matches_processed"],
                "total_participations_evaluated": self.audit["total_participations_evaluated"],
                "active_player_states_by_format": current_counts,
                "history_checkpoints_materialized": history_count,
                "pre_match_snapshots_materialized": snapshot_count,
                "elapsed_seconds": self.audit["elapsed_seconds"],
            },
            audit_records=self.audit,
        )
        print(f"[ChronologicalEngine] Successfully materialized rating store v4 to: {self.output_dir}")
        print(f"[ChronologicalEngine] Manifest generated: {manifest_path}")

        return {
            "status": "SUCCESS",
            "current_counts": current_counts,
            "history_count": history_count,
            "snapshot_count": snapshot_count,
            "manifest_path": str(manifest_path),
            "audit": self.audit,
        }
