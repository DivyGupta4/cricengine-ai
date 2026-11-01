"""
CricEngine AI — Entry Point Script for Rating Pipeline Execution (Phase 4B)
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ratings.chronological_engine import ChronologicalRatingEngine
from src.ratings.validation import RatingValidator
from src.ratings.config import RATING_STORE_V4_DIR


def main():
    print("=" * 70)
    print("CRICENGINE AI — PHASE 4B: PLAYER RATING ENGINE EXECUTION")
    print("Context-Adjusted Hierarchical Bayesian State-Space (CA-HBSS)")
    print("=" * 70)
    
    engine = ChronologicalRatingEngine()
    results = engine.run_pipeline()
    
    print("\n" + "=" * 70)
    print("EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Status: {results['status']}")
    print(f"Total Matches Processed: {results['audit']['total_matches_processed']:,}")
    print(f"Total Participations Evaluated: {results['audit']['total_participations_evaluated']:,}")
    print(f"Batting Updates Applied: {results['audit']['batting_observations_updated']:,}")
    print(f"Bowling Updates Applied: {results['audit']['bowling_observations_updated']:,}")
    print(f"Fielding Updates Applied: {results['audit']['fielding_observations_updated']:,}")
    print(f"Zero Exposure Skips: {results['audit']['zero_exposure_skips']:,}")
    print(f"Identity Uncertain (c65e0275) Evaluated: {results['audit']['identity_uncertain_evaluations']:,}")
    print(f"Numerical Failures: {results['audit']['numerical_failures']:,}")
    print(f"Elapsed Time: {results['audit']['elapsed_seconds']}s")
    print("\nActive Player States by Format:")
    for fmt, cnt in results["current_counts"].items():
        print(f"  {fmt}: {cnt:,} players")
    print(f"\nHistorical Checkpoints Materialized: {results['history_count']:,}")
    print(f"Pre-Match Snapshots Materialized: {results['snapshot_count']:,}")
    print(f"Manifest Path: {results['manifest_path']}")
    print("=" * 70)

    # Run validation
    validator = RatingValidator(RATING_STORE_V4_DIR)
    val_results = validator.evaluate_holdout()
    print("\nHOLDOUT EVALUATION SUMMARY:")
    print(val_results)


if __name__ == "__main__":
    main()
